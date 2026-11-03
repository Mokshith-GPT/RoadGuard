const CLASS_INFO = [
  { code: "D00", name: "Longitudinal crack" },
  { code: "D10", name: "Transverse crack" },
  { code: "D20", name: "Alligator / fatigue crack" },
  { code: "D40", name: "Pothole" }
];

function allowedOrigins(env) {
  return (env.ALLOWED_ORIGINS || "https://mokshith-gpt.github.io,http://localhost:8080,http://127.0.0.1:8080")
    .split(",").map(x => x.trim()).filter(Boolean);
}

function corsHeaders(request, env) {
  const origin = request.headers.get("Origin");
  const allowed = allowedOrigins(env);
  const headers = {
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400"
  };
  if (origin && allowed.includes(origin)) headers["Access-Control-Allow-Origin"] = origin;
  return headers;
}

function json(data, status, headers) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...(headers || {}) }
  });
}

function base64url(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function decodeBase64url(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

async function createSession(user, secret) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url(new TextEncoder().encode(JSON.stringify({ alg: "HS256", typ: "JWT" })));
  const payload = base64url(new TextEncoder().encode(JSON.stringify({
    sub: user.sub, email: user.email, name: user.name || "",
    picture: user.picture || "", iat: now, exp: now + 6 * 60 * 60
  })));
  const unsigned = header + "." + payload;
  const signature = await crypto.subtle.sign("HMAC", await hmacKey(secret), new TextEncoder().encode(unsigned));
  return unsigned + "." + base64url(new Uint8Array(signature));
}

async function verifySession(request, env) {
  if (!env.SESSION_SECRET) throw new Error("SESSION_SECRET_NOT_CONFIGURED");
  const authorization = request.headers.get("Authorization") || "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("UNAUTHORIZED");
  const unsigned = parts[0] + "." + parts[1];
  const valid = await crypto.subtle.verify("HMAC", await hmacKey(env.SESSION_SECRET), decodeBase64url(parts[2]), new TextEncoder().encode(unsigned));
  if (!valid) throw new Error("UNAUTHORIZED");
  let payload;
  try { payload = JSON.parse(new TextDecoder().decode(decodeBase64url(parts[1]))); }
  catch (_) { throw new Error("UNAUTHORIZED"); }
  if (!payload.exp || payload.exp < Math.floor(Date.now() / 1000)) throw new Error("SESSION_EXPIRED");
  return payload;
}

function validateEmail(value) {
  return typeof value === "string" && value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

async function googleAuth(request, env) {
  if (!env.GOOGLE_CLIENT_ID || !env.SESSION_SECRET) {
    return json({ error: "GOOGLE_OAUTH_NOT_CONFIGURED", message: "Set GOOGLE_CLIENT_ID and SESSION_SECRET in Worker settings." }, 503);
  }
  const body = await request.json();
  if (typeof body.credential !== "string" || body.credential.length > 12000) {
    return json({ error: "INVALID_GOOGLE_CREDENTIAL" }, 400);
  }
  const tokenInfoUrl = "https://oauth2.googleapis.com/tokeninfo?id_token=" + encodeURIComponent(body.credential);
  const response = await fetch(tokenInfoUrl, { headers: { "Accept": "application/json" } });
  if (!response.ok) return json({ error: "GOOGLE_TOKEN_REJECTED" }, 401);
  const claims = await response.json();
  if (claims.aud !== env.GOOGLE_CLIENT_ID || claims.email_verified !== "true" || !claims.sub || !validateEmail(claims.email)) {
    return json({ error: "GOOGLE_IDENTITY_NOT_VERIFIED" }, 401);
  }
  const user = { sub: claims.sub, email: claims.email, name: claims.name || "", picture: claims.picture || "" };
  const sessionToken = await createSession(user, env.SESSION_SECRET);
  return json({ success: true, sessionToken: sessionToken, expiresIn: 21600, user: user });
}

async function inspectImage(request, env) {
  await verifySession(request, env);
  if (!env.MODEL_API_URL) {
    return json({
      error: "MODEL_NOT_CONFIGURED",
      message: "No trained road-damage inference endpoint is configured. No detection result has been fabricated.",
      supportedClasses: CLASS_INFO
    }, 503);
  }
  const body = await request.json();
  if (typeof body.image_base64 !== "string" || body.image_base64.length < 100 || body.image_base64.length > 9000000) {
    return json({ error: "INVALID_IMAGE", message: "Provide image_base64 between 100 bytes and 6.5 MB encoded." }, 400);
  }
  const response = await fetch(env.MODEL_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(env.MODEL_API_TOKEN ? { "Authorization": "Bearer " + env.MODEL_API_TOKEN } : {})
    },
    body: JSON.stringify({
      image_base64: body.image_base64,
      filename: String(body.filename || "road-image").slice(0, 160),
      metadata: body.metadata || {}
    })
  });
  if (!response.ok) return json({ error: "MODEL_UPSTREAM_ERROR", upstreamStatus: response.status }, 502);
  const result = await response.json().catch(() => null);
  if (!result || !Array.isArray(result.detections)) {
    return json({ error: "MODEL_RESPONSE_INVALID", message: "The inference service must return a detections array." }, 502);
  }
  return json({
    success: true,
    source: "configured-model",
    overall_severity: result.overall_severity || "Not scored",
    overall_score: Number.isFinite(result.overall_score) ? result.overall_score : null,
    damage_area_percentage: Number.isFinite(result.damage_area_percentage) ? result.damage_area_percentage : null,
    total_defects_count: result.detections.length,
    detections: result.detections,
    timestamp: new Date().toISOString()
  });
}

async function sendEmail(request, env) {
  await verifySession(request, env);
  if (!env.RESEND_API_KEY || !env.REPORT_FROM_EMAIL) {
    return json({ error: "EMAIL_NOT_CONFIGURED", message: "Configure RESEND_API_KEY and REPORT_FROM_EMAIL in Cloudflare Worker settings." }, 503);
  }
  const body = await request.json();
  if (body.confirmSend !== true) return json({ error: "EXPLICIT_CONFIRMATION_REQUIRED" }, 400);
  if (!validateEmail(body.to)) return json({ error: "INVALID_RECIPIENT_EMAIL" }, 400);
  if (typeof body.subject !== "string" || body.subject.length > 180 || typeof body.text !== "string" || body.text.length > 12000) {
    return json({ error: "INVALID_EMAIL_CONTENT" }, 400);
  }
  const attachments = [];
  if (body.attachment) {
    const a = body.attachment;
    if (typeof a.content_base64 !== "string" || a.content_base64.length > 7000000) {
      return json({ error: "ATTACHMENT_TOO_LARGE", message: "Image attachments must be below approximately 5 MB." }, 413);
    }
    const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!allowedTypes.includes(a.content_type)) return json({ error: "UNSUPPORTED_ATTACHMENT_TYPE" }, 400);
    attachments.push({
      filename: String(a.filename || "road-evidence.jpg").replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 120),
      content: a.content_base64
    });
  }
  const upstream = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { "Authorization": "Bearer " + env.RESEND_API_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.REPORT_FROM_EMAIL,
      to: [body.to],
      subject: body.subject,
      text: body.text,
      ...(attachments.length ? { attachments: attachments } : {})
    })
  });
  const result = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return json({ error: "EMAIL_PROVIDER_ERROR", message: result.message || "Resend rejected the request." }, 502);
  return json({ success: true, id: result.id || null });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(request, env);
    const origin = request.headers.get("Origin");
    if (origin && !allowedOrigins(env).includes(origin)) return json({ error: "ORIGIN_NOT_ALLOWED" }, 403, cors);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    try {
      if (url.pathname === "/" || url.pathname === "/health") {
        return json({
          status: "online",
          service: env.APP_NAME || "RoadGuard API",
          version: env.VERSION || "2.0.0",
          runtime: "Cloudflare Workers",
          modelConfigured: !!env.MODEL_API_URL,
          emailConfigured: !!(env.RESEND_API_KEY && env.REPORT_FROM_EMAIL),
          googleAuthConfigured: !!(env.GOOGLE_CLIENT_ID && env.SESSION_SECRET),
          supportedClasses: CLASS_INFO,
          storage: "Evidence images and dashcam clips are stored locally in the client app."
        }, 200, cors);
      }
      if (url.pathname === "/api/v1/auth/google" && request.method === "POST") {
        const response = await googleAuth(request, env);
        return new Response(response.body, { status: response.status, headers: { ...Object.fromEntries(response.headers), ...cors } });
      }
      if (url.pathname === "/api/v1/inspect" && request.method === "POST") {
        const response = await inspectImage(request, env);
        return new Response(response.body, { status: response.status, headers: { ...Object.fromEntries(response.headers), ...cors } });
      }
      if (url.pathname === "/api/v1/reports/email" && request.method === "POST") {
        const response = await sendEmail(request, env);
        return new Response(response.body, { status: response.status, headers: { ...Object.fromEntries(response.headers), ...cors } });
      }
      if (url.pathname.startsWith("/api/v1/audit/")) {
        return json({ error: "AUDIT_STORAGE_NOT_CONFIGURED", message: "Durable cloud audit storage is not configured. Use the local evidence album or add a Cloudflare D1/R2 binding." }, 501, cors);
      }
      return json({ error: "NOT_FOUND" }, 404, cors);
    } catch (error) {
      const message = error && error.message ? error.message : "Unexpected server error";
      if (message === "UNAUTHORIZED" || message === "SESSION_EXPIRED") return json({ error: message }, 401, cors);
      if (message === "SESSION_SECRET_NOT_CONFIGURED") return json({ error: "SESSION_SECRET_NOT_CONFIGURED" }, 503, cors);
      console.error("RoadGuard Worker error:", message);
      return json({ error: "INTERNAL_ERROR" }, 500, cors);
    }
  }
};
