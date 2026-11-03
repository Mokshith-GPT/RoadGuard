# RoadGuard deployment and integration guide

## Current build boundaries

The browser app is a static PWA in `web/`. It stores images, metadata, and up to two completed video clips in the current browser's IndexedDB. The Android app records MP4 segments to app-specific storage and retains the two newest completed clips. Neither client is a central evidence archive.

The image-analysis fallback in the PWA is a **classical computer-vision candidate extractor** (dark connected regions in a road-area crop). It is not a trained pothole classifier and does not produce ground-truth D00/D10/D20/D40 predictions. The Cloudflare Worker deliberately returns `503 MODEL_NOT_CONFIGURED` until a real model inference API is configured. This prevents fabricated results from being presented as AI detections.

## 1. GitHub Pages

The `.github/workflows/deploy-pages.yml` workflow publishes `web/` on pushes to `main`.

1. Open **Settings → Pages** in the repository and set **Build and deployment → Source** to **GitHub Actions**.
2. Push to `main` or run **Actions → Deploy RoadGuard PWA to GitHub Pages → Run workflow**.
3. When the workflow succeeds, the site URL for this repository is normally:
   `https://mokshith-gpt.github.io/RoadGuard/`

The web app is an installable PWA on browsers that support installation. Camera access requires HTTPS (GitHub Pages qualifies) and explicit user permission. A browser tab can be suspended or killed by the operating system; do not rely on a browser PWA for unattended dashcam recording.

## 2. Google OAuth

1. Create a Google OAuth 2.0 **Web application** client in Google Cloud Console.
2. Add the authorized JavaScript origin `https://mokshith-gpt.github.io` (or your actual custom-domain origin). For local development add `http://localhost:8080`.
3. Put the Web Client ID into `web/app-config.js` as `googleClientId`.
4. Add the same client ID as a Cloudflare Worker variable named `GOOGLE_CLIENT_ID`.
5. Set a random, high-entropy Worker secret named `SESSION_SECRET`.

Google GIS returns a credential to the browser; the Worker verifies it with Google's tokeninfo endpoint and creates a short-lived HMAC session. Never place `SESSION_SECRET`, provider API keys, or model tokens in `web/app-config.js`.

## 3. Cloudflare Worker

The source is in `cloudflare-backend/`. The GitHub Actions deploy workflow expects a repository Actions secret named `CLOUDFLARE_API_TOKEN` with permission to deploy Workers. Add this under **Settings → Secrets and variables → Actions**. The workflow skips the deploy step if the secret is missing; it does not claim deployment succeeded.

Set these Worker variables/secrets:

| Name | Type | Purpose |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Variable | Same Google Web Client ID used by the PWA |
| `SESSION_SECRET` | Secret | Signs and verifies short-lived app sessions |
| `MODEL_API_URL` | Variable | HTTPS endpoint for your deployed trained CV model |
| `MODEL_API_TOKEN` | Secret (optional) | Bearer token for the model API |
| `RESEND_API_KEY` | Secret | Resend API key for authorized report email |
| `REPORT_FROM_EMAIL` | Variable | Verified sender identity in Resend |
| `ALLOWED_ORIGINS` | Variable | Comma-separated allowed browser origins |

The model endpoint must accept JSON containing `image_base64`, `filename`, and `metadata`, and return a JSON object with a `detections` array. Optional response fields are `overall_severity`, `overall_score`, and `damage_area_percentage`. A Python service can load `models/best.pt` with Ultralytics and expose this contract. Do not point `MODEL_API_URL` at a demo endpoint that fabricates detections.

Deploy manually from `cloudflare-backend/` with Wrangler after `npx wrangler login`, or add `CLOUDFLARE_API_TOKEN` to GitHub Actions and push a change under `cloudflare-backend/`. The pre-existing Worker URL in the original README is not proof that this updated Worker has been deployed; verify `GET /health` after deployment.

The Worker does not persist cloud audit logs. Evidence remains local to each device. Add Cloudflare D1/R2 (with ownership, retention and deletion policy) before building shared multi-device albums.

## 4. Municipal email reporting

1. Verify the municipal or public-works office's actual email address independently.
2. Configure a Resend API key and verify the sender domain/address.
3. Add `RESEND_API_KEY` and `REPORT_FROM_EMAIL` to Worker secrets/variables.
4. Sign in, choose an evidence image, enter the intended recipient and contact details, review the message, and explicitly confirm sending.

Email delivery is never automatic. The recipient address is user-supplied; RoadGuard does not guess which authority is responsible for a road. The mailto fallback opens a draft and downloads the image separately because mailto links cannot reliably attach files.

## 5. Android APK

The Android project is under `android/`. The updated CameraX dashcam activity stores SD-quality MP4 segments under the app's external Movies folder and removes completed clips beyond the latest two. Still evidence frames and JSON sidecars are stored under the app's Pictures folder. Android recording stops when the activity leaves the foreground.

The current APK workflow is a college/demo build and uses the debug signing configuration. Before Google Play distribution, configure a private release keystore in GitHub Actions secrets; never commit the keystore or passwords. The generated APK is available as a workflow/release asset after a successful build.

## 6. Vehicle dashcam and CCTV limitations

- A phone mounted in a vehicle can use the Android app while the app remains visible and the device is safely mounted. The driver must not interact with the screen while driving.
- Reliable screen-off/background dashcam operation requires an Android foreground camera service, boot/restart policy, thermal/storage controls, and testing against target-device restrictions. It is not enabled by this demo build.
- Traffic/security CCTV integration is a separate adapter project. IP cameras commonly expose RTSP/ONVIF streams; a server-side ingestion gateway must authenticate to the camera, decode frames, and call the model API. A browser page cannot directly open arbitrary RTSP camera feeds.
- Do not deploy this academic prototype as a safety-critical or regulatory road inspection system without validated model metrics, calibration, security review, and a human inspection process.

## 7. Local development

Serve `web/` from a local HTTP server (not by opening the HTML file directly):

```bash
cd web
python -m http.server 8080
```

Open `http://localhost:8080`. Configure OAuth and the Worker separately. For the existing Python inspection dashboard, follow the root README and install `requirements.txt`.
