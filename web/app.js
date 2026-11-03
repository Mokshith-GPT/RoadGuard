(() => {
  "use strict";
  const CFG = window.ROADGUARD_CONFIG || {};
  const API_DEFAULT = CFG.apiBase || "";
  const DB_NAME = "roadguard-local-v1";
  const DB_VERSION = 1;
  const state = {
    db: null, records: [], videos: [], session: null, user: null,
    stream: null, recorder: null, chunks: [], recording: false,
    segmentTimer: null, frameTimer: null, analyzingFrame: false,
    lastAutoCapture: 0, currentUpload: null, selectedRecord: null,
    installPrompt: null, reports: []
  };
  const $ = id => document.getElementById(id);
  const apiUrl = () => (localStorage.getItem("roadguard-api") || API_DEFAULT).replace(/\/$/, "");
  const sessionToken = () => state.session || sessionStorage.getItem("roadguard-session") || "";

  function toast(message) {
    const el = $("toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("show"), 3400);
  }
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("images")) db.createObjectStore("images", {keyPath:"id"});
        if (!db.objectStoreNames.contains("videos")) db.createObjectStore("videos", {keyPath:"id"});
        if (!db.objectStoreNames.contains("reports")) db.createObjectStore("reports", {keyPath:"id"});
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  function dbAction(store, mode, action) {
    return new Promise((resolve, reject) => {
      const tx = state.db.transaction(store, mode);
      const req = action(tx.objectStore(store));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  const dbPut = (store, item) => dbAction(store, "readwrite", s => s.put(item));
  const dbDelete = (store, id) => dbAction(store, "readwrite", s => s.delete(id));
  const dbAll = store => dbAction(store, "readonly", s => s.getAll());
  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }
  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }
  function getPosition() {
    return new Promise(resolve => {
      if (!navigator.geolocation) return resolve(null);
      navigator.geolocation.getCurrentPosition(pos => resolve({
        latitude: Number(pos.coords.latitude.toFixed(6)),
        longitude: Number(pos.coords.longitude.toFixed(6)),
        accuracy: Math.round(pos.coords.accuracy || 0)
      }), () => resolve(null), {enableHighAccuracy:true, timeout:8000, maximumAge:15000});
    });
  }
  async function reverseAddress(position) {
    if (!position) return "Location not available";
    try {
      const q = new URLSearchParams({format:"jsonv2",lat:position.latitude,lon:position.longitude});
      const r = await fetch("https://nominatim.openstreetmap.org/reverse?" + q.toString(), {headers:{"Accept":"application/json"}});
      if (!r.ok) return position.latitude + ", " + position.longitude;
      const data = await r.json();
      return (data.display_name || (position.latitude + ", " + position.longitude)).slice(0,240);
    } catch (_) {
      return position.latitude + ", " + position.longitude;
    }
  }
  async function metadata(source, filename) {
    const geo = await getPosition();
    const address = await reverseAddress(geo);
    return {
      capturedAt:new Date().toISOString(),
      source:source,
      filename:filename || "capture.jpg",
      latitude:geo ? geo.latitude : null,
      longitude:geo ? geo.longitude : null,
      accuracyMeters:geo ? geo.accuracy : null,
      address:address,
      device:navigator.userAgent.slice(0,180),
      locationPermission:!!geo
    };
  }

  function browserCV(blob) {
    return new Promise((resolve, reject) => {
      createImageBitmap(blob).then(bitmap => {
        const maxSide = 420;
        const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
        const w = Math.max(1, Math.round(bitmap.width * scale));
        const h = Math.max(1, Math.round(bitmap.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext("2d", {willReadFrequently:true});
        ctx.drawImage(bitmap, 0, 0, w, h);
        bitmap.close();
        const frame = ctx.getImageData(0, 0, w, h);
        const px = frame.data;
        const gray = new Uint8Array(w * h);
        const hist = new Uint32Array(256);
        let sum = 0, sampleCount = 0;
        for (let y = Math.floor(h * .42); y < h; y++) {
          for (let x = Math.floor(w * .08); x < Math.floor(w * .92); x++) {
            const i = (y * w + x) * 4;
            const g = Math.round(.299 * px[i] + .587 * px[i+1] + .114 * px[i+2]);
            gray[y*w+x] = g; hist[g]++; sum += g; sampleCount++;
          }
        }
        const mean = sampleCount ? sum / sampleCount : 0;
        const threshold = Math.max(26, Math.min(105, mean - 31));
        const visited = new Uint8Array(w * h);
        const queue = new Int32Array(w * h);
        const candidates = [];
        let candidatePixels = 0;
        const yStart = Math.floor(h * .42), xStart = Math.floor(w * .08), xEnd = Math.floor(w * .92);
        for (let y = yStart; y < h; y += 1) {
          for (let x = xStart; x < xEnd; x += 1) {
            const origin = y*w+x;
            if (visited[origin] || gray[origin] >= threshold) continue;
            let head = 0, tail = 0;
            queue[tail++] = origin; visited[origin] = 1;
            let minX=x,maxX=x,minY=y,maxY=y,area=0;
            while (head < tail) {
              const p = queue[head++]; const py = Math.floor(p/w), px0 = p - py*w;
              area++; if(px0<minX)minX=px0;if(px0>maxX)maxX=px0;if(py<minY)minY=py;if(py>maxY)maxY=py;
              const neighbours = [p-1,p+1,p-w,p+w];
              for (let k=0;k<4;k++) {
                const n=neighbours[k];
                if(n<0||n>=w*h)continue;
                const ny=Math.floor(n/w), nx=n-ny*w;
                if(nx<xStart||nx>=xEnd||ny<yStart||ny>=h||visited[n]||gray[n]>=threshold)continue;
                visited[n]=1;queue[tail++]=n;
              }
            }
            if(area>=7 && area < (w*h*.055) && maxX-minX>=2 && maxY-minY>=2) {
              candidatePixels += area;
              candidates.push({x:minX,y:minY,w:maxX-minX+1,h:maxY-minY+1,area:area});
            }
          }
        }
        candidates.sort((a,b)=>b.area-a.area);
        const selected = candidates.slice(0,12);
        ctx.lineWidth = Math.max(1.5, w/260);
        selected.forEach((c,i) => {
          ctx.strokeStyle = "#ff2800";
          ctx.fillStyle = "rgba(255,40,0,.12)";
          ctx.fillRect(c.x,c.y,c.w,c.h);
          ctx.strokeRect(c.x,c.y,c.w,c.h);
          ctx.fillStyle = "#ff2800";
          ctx.font = "bold " + Math.max(9,w/36) + "px sans-serif";
          ctx.fillText("CANDIDATE " + (i+1), c.x, Math.max(10,c.y-4));
        });
        const roiPixels = Math.max(1, (h-yStart)*(xEnd-xStart));
        const areaPct = Number((candidatePixels/roiPixels*100).toFixed(2));
        const severity = areaPct >= 8 ? "High candidate coverage" : areaPct >= 2 ? "Moderate candidate coverage" : "Low candidate coverage";
        canvas.toBlob(overlayBlob => resolve({
          method:"Browser CV baseline (adaptive dark-region candidates)",
          candidateCount:selected.length,
          areaPct:areaPct,
          severity:severity,
          threshold:threshold,
          overlayBlob:overlayBlob,
          sourceWidth:w,sourceHeight:h,
          disclaimer:"Candidate regions are heuristic dark/irregular areas, not confirmed potholes or a trained D00/D10/D20/D40 prediction."
        }),"image/jpeg",.88);
      }).catch(reject);
    });
  }

  async function modelInspect(blob, meta) {
    const base = apiUrl();
    if (!base) return null;
    const token = sessionToken();
    if (!token) return null;
    const image = await blobToBase64(blob);
    const res = await fetch(base + "/api/v1/inspect", {
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":"Bearer " + token},
      body:JSON.stringify({image_base64:image,filename:meta.filename,metadata:meta})
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (res.status === 503 || res.status === 404) return null;
      throw new Error(data.error || ("Inference service error " + res.status));
    }
    const data = await res.json();
    if (!Array.isArray(data.detections)) throw new Error("The model response did not include a detections array.");
    return data;
  }

  async function inspectBlob(blob, meta) {
    let model = null;
    try { model = await modelInspect(blob, meta); }
    catch (err) { console.warn(err); toast("Model unavailable: " + err.message + ". Using the browser CV baseline."); }
    if (model) {
      return {
        method:"Configured road-damage model",
        candidateCount:model.detections.length,
        areaPct:Number(model.damage_area_percentage || 0),
        severity:model.overall_severity || "Not scored",
        detections:model.detections,
        overlayBlob:null,
        disclaimer:"Model output is experimental and must be reviewed by a human inspector."
      };
    }
    return browserCV(blob);
  }

  async function refreshData() {
    state.records = (await dbAll("images")).sort((a,b)=>b.createdAt-a.createdAt);
    state.videos = (await dbAll("videos")).sort((a,b)=>b.createdAt-a.createdAt);
    state.reports = (await dbAll("reports")).sort((a,b)=>b.createdAt-a.createdAt);
    renderAll();
  }
  function imageUrl(item) { return URL.createObjectURL(item.overlayBlob || item.blob); }
  function shortDate(iso) {
    try { return new Date(iso).toLocaleString([], {dateStyle:"medium",timeStyle:"short"}); } catch (_) { return iso || ""; }
  }
  function renderAll() {
    $("album-count").textContent = String(state.records.length);
    $("metric-images").textContent = String(state.records.length);
    $("metric-videos").textContent = state.videos.length + " / 2";
    $("metric-located").textContent = String(state.records.filter(x=>x.metadata && x.metadata.latitude!=null).length);
    $("metric-reports").textContent = String(state.reports.length);
    renderRecent(); renderAlbum(); renderReportOptions(); updateReportPreview();
  }
  function renderRecent() {
    const target = $("recent-list");
    if (!state.records.length) {
      target.innerHTML = '<div class="empty-state"><span>▧</span><strong>No captures yet</strong><p>Start a live inspection or upload a road image to build your evidence album.</p></div>';
      return;
    }
    target.innerHTML = state.records.slice(0,4).map(item =>
      '<div class="recent-row"><img src="' + imageUrl(item) + '" alt=""><div><strong>' + esc(item.metadata.filename) + '</strong><small>' + esc(shortDate(item.metadata.capturedAt)) + ' · ' + esc(item.analysis.method) + '</small></div><button data-report="' + esc(item.id) + '">Use in report</button></div>'
    ).join("");
    target.querySelectorAll("[data-report]").forEach(btn=>btn.addEventListener("click",()=>{navigate("reports");$("report-record").value=btn.dataset.report;updateReportPreview();}));
  }
  function renderAlbum() {
    const target = $("album-grid");
    const query = ($("album-search").value || "").toLowerCase().trim();
    const items = state.records.filter(item => {
      const m=item.metadata||{};
      return [m.filename,m.address,m.capturedAt,m.source].join(" ").toLowerCase().includes(query);
    });
    $("album-summary").textContent = items.length + " image" + (items.length===1?"":"s") + " · " + state.videos.length + " video clips";
    if (!items.length) {
      target.innerHTML = '<div class="empty-state"><span>▧</span><strong>' + (query?"No matching evidence":"Your album is empty") + '</strong><p>Images captured or uploaded on this device will appear here.</p></div>';
      return;
    }
    target.innerHTML = items.map(item => {
      const m=item.metadata||{}, a=item.analysis||{};
      const gps=m.latitude==null?"GPS not available":m.latitude.toFixed(5)+", "+m.longitude.toFixed(5);
      return '<article class="album-card"><img src="' + imageUrl(item) + '" alt="Inspection evidence"><div class="album-card-body"><strong>' + esc(m.filename) + '</strong><small>' + esc(shortDate(m.capturedAt)) + '<br>' + esc(m.address || gps) + '</small><small>' + esc(a.candidateCount || 0) + ' candidate regions · ' + esc(a.areaPct || 0) + '% candidate area</small><div class="album-card-actions"><button data-use="' + esc(item.id) + '">Prepare report</button><button data-download="' + esc(item.id) + '">Download</button><button data-delete="' + esc(item.id) + '">Delete</button></div></div></article>';
    }).join("");
    target.querySelectorAll("[data-use]").forEach(btn=>btn.addEventListener("click",()=>{navigate("reports");$("report-record").value=btn.dataset.use;updateReportPreview();}));
    target.querySelectorAll("[data-download]").forEach(btn=>btn.addEventListener("click",()=>{const item=state.records.find(x=>x.id===btn.dataset.download);if(item)downloadBlob(item.overlayBlob||item.blob,item.metadata.filename.replace(/\.[^.]+$/,"")+"_roadguard.jpg");}));
    target.querySelectorAll("[data-delete]").forEach(btn=>btn.addEventListener("click",async()=>{if(confirm("Delete this image and its metadata from this device?")){await dbDelete("images",btn.dataset.delete);await refreshData();toast("Evidence deleted.");}}));
  }
  function renderReportOptions() {
    const select=$("report-record"), current=select.value;
    select.innerHTML='<option value="">Select an evidence image</option>'+state.records.map(x=>'<option value="'+esc(x.id)+'">'+esc(x.metadata.filename)+' — '+esc(shortDate(x.metadata.capturedAt))+'</option>').join("");
    if(state.records.some(x=>x.id===current))select.value=current;
  }
  function selectedEvidence() { return state.records.find(x=>x.id===$("report-record").value) || null; }
  function buildReportText(item) {
    const m=item.metadata||{}, a=item.analysis||{};
    const location=m.address || (m.latitude!=null?m.latitude+", "+m.longitude:"Not available");
    const recipient=$("recipient-email").value.trim();
    const authority=$("road-authority").value.trim() || "the relevant road-maintenance authority";
    const contact=$("report-contact").value.trim() || "Not provided";
    const notes=$("report-notes").value.trim() || "Please inspect the location and advise on the maintenance action.";
    const subject="Road surface damage reported for inspection";
    const body="Dear "+authority+" Team,\n\nI am writing to request an inspection of a road-surface issue observed at the location below.\n\nLocation: "+location+"\nCoordinates: "+(m.latitude==null?"Not available":m.latitude+", "+m.longitude)+"\nObserved at: "+shortDate(m.capturedAt)+"\nEvidence file: "+m.filename+"\nVisual analysis: "+(a.candidateCount||0)+" candidate region(s), "+(a.areaPct||0)+"% candidate area ("+(a.method||"not available")+")\n\nAdditional details: "+notes+"\n\nPlease confirm whether this location falls under your jurisdiction and advise the appropriate maintenance team. The attached image is supplied as supporting evidence; the visual analysis is preliminary and should not be treated as an engineering assessment.\n\nRegards,\nRoadGuard User\nContact: "+contact+"\n";
    return {subject,body,recipient};
  }
  function updateReportPreview() {
    const item=selectedEvidence(), target=$("report-preview");
    $("download-report").disabled=!item;
    if(!item){target.innerHTML="<strong>Subject: Road surface damage reported for inspection</strong><p>Select an evidence image to populate the report preview.</p>";return;}
    const r=buildReportText(item);
    target.textContent="To: "+(r.recipient||"[enter verified office email]")+"\nSubject: "+r.subject+"\n\n"+r.body;
  }
  async function saveImage(blob, name, source) {
    const meta=await metadata(source,name);
    const analysis=await inspectBlob(blob,meta);
    const item={id:"img-"+Date.now()+"-"+Math.random().toString(36).slice(2,7),createdAt:Date.now(),blob:blob,overlayBlob:analysis.overlayBlob||null,metadata:meta,analysis:analysis};
    await dbPut("images",item);
    await refreshData();
    return item;
  }

  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return toast("Camera access requires HTTPS and a supported browser.");
    try {
      const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:"environment"},width:{ideal:1280},height:{ideal:720}}});
      state.stream=stream;
      const video=$("camera-preview"); video.srcObject=stream; video.style.display="block"; $("camera-placeholder").style.display="none";
      await video.play().catch(()=>{});
      $("camera-heading").textContent="Rear camera active";
      $("stream-state").textContent="Online";
      $("start-camera").disabled=true; $("stop-camera").disabled=false; $("toggle-record").disabled=false;
      const pos=await getPosition();
      $("location-state").textContent=pos?"GPS tagged":"GPS unavailable";
      $("gps-hud").textContent=pos?"GPS · "+pos.latitude.toFixed(4)+", "+pos.longitude.toFixed(4):"GPS · unavailable";
      toast("Camera is active. Keep the device mounted and the page visible.");
    } catch(err) { toast("Camera permission or hardware error: "+err.message); }
  }
  function mimeForVideo() {
    const choices=["video/mp4;codecs=h264","video/webm;codecs=vp9","video/webm;codecs=vp8","video/webm"];
    return choices.find(type=>window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || "";
  }
  function startVideoSegment() {
    if(!state.stream || !state.recording)return;
    try {
      const mime=mimeForVideo();
      const recorder=new MediaRecorder(state.stream,mime?{mimeType:mime,videoBitsPerSecond:1800000}:{videoBitsPerSecond:1800000});
      state.recorder=recorder; state.chunks=[];
      recorder.ondataavailable=event=>{if(event.data && event.data.size)state.chunks.push(event.data);};
      recorder.onstop=async()=>{
        const blob=new Blob(state.chunks,{type:recorder.mimeType||"video/webm"});
        state.chunks=[];
        if(blob.size>0){
          const created=new Date().toISOString();
          const filename="RoadGuard_"+created.replace(/[:.]/g,"-")+(blob.type.includes("mp4")?".mp4":".webm");
          const meta=await metadata("dashcam-video",filename);
          await dbPut("videos",{id:"vid-"+Date.now()+"-"+Math.random().toString(36).slice(2,6),createdAt:Date.now(),blob:blob,filename:filename,mimeType:blob.type,metadata:meta,size:blob.size});
          await pruneVideos();
          $("metric-videos").textContent=state.videos.length+" / 2";
          toast("Video clip saved locally ("+(blob.size/1024/1024).toFixed(1)+" MB).");
        }
        if(state.recording && state.stream) startVideoSegment();
      };
      recorder.start(1000);
      state.segmentTimer=setTimeout(()=>{if(state.recording && state.recorder===recorder && recorder.state==="recording")recorder.stop();},60000);
      $("record-status").classList.add("recording"); $("record-status").innerHTML="<i></i> RECORDING";
      $("toggle-record").textContent="■ Stop recording";
      $("record-state").textContent="Recording";
    } catch(err) { state.recording=false; toast("Video recording could not start: "+err.message); }
  }
  async function pruneVideos() {
    const all=(await dbAll("videos")).sort((a,b)=>b.createdAt-a.createdAt);
    for(const item of all.slice(2))await dbDelete("videos",item.id);
    state.videos=all.slice(0,2);
  }
  async function toggleRecording() {
    if(state.recording){
      state.recording=false; clearTimeout(state.segmentTimer);
      if(state.recorder && state.recorder.state==="recording")state.recorder.stop();
      $("record-status").classList.remove("recording"); $("record-status").innerHTML="<i></i> CAMERA READY";
      $("toggle-record").textContent="● Start recording"; $("record-state").textContent="Stopped";
      return;
    }
    if(!state.stream)return toast("Start the camera first.");
    const ok=confirm("Storage warning: RoadGuard retains only the two latest completed video clips. Older clips beyond that limit will be deleted from this app's local storage. Continue?");
    if(!ok)return;
    await pruneVideos();
    state.recording=true; startVideoSegment(); toast("Dashcam recording started. A new clip is created every 60 seconds.");
  }
  async function stopCamera() {
    if(state.recording){state.recording=false;clearTimeout(state.segmentTimer);if(state.recorder&&state.recorder.state==="recording")state.recorder.stop();}
    if(state.frameTimer)clearInterval(state.frameTimer);
    if(state.stream)state.stream.getTracks().forEach(track=>track.stop());
    state.stream=null;state.recorder=null;
    const video=$("camera-preview");video.srcObject=null;video.style.display="none";
    $("camera-placeholder").style.display="flex";$("camera-heading").textContent="Camera not started";
    $("stream-state").textContent="Offline";$("record-state").textContent="Stopped";
    $("start-camera").disabled=false;$("stop-camera").disabled=true;$("toggle-record").disabled=true;
    $("record-status").classList.remove("recording");$("record-status").innerHTML="<i></i> STANDBY";$("toggle-record").textContent="● Start recording";
    toast("Camera stopped.");
  }
  async function analyzeLiveFrame() {
    if(state.analyzingFrame || !state.stream || !state.recording)return;
    state.analyzingFrame=true;
    try {
      const video=$("camera-preview");
      if(video.readyState<2)return;
      const canvas=document.createElement("canvas");canvas.width=video.videoWidth;canvas.height=video.videoHeight;
      canvas.getContext("2d").drawImage(video,0,0);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/jpeg",.82));
      if(!blob)return;
      const analysis=await browserCV(blob);
      $("analysis-state").textContent=analysis.candidateCount+" candidate(s)";
      if(analysis.candidateCount>0 && Date.now()-state.lastAutoCapture>15000){
        state.lastAutoCapture=Date.now();
        const meta=await metadata("dashcam-frame","Dashcam frame "+new Date().toLocaleTimeString()+".jpg");
        const item={id:"img-"+Date.now()+"-"+Math.random().toString(36).slice(2,7),createdAt:Date.now(),blob:blob,overlayBlob:analysis.overlayBlob,metadata:meta,analysis:analysis};
        await dbPut("images",item);await refreshData();
        const event=document.createElement("div");event.className="event-item";event.innerHTML="<strong>"+esc(analysis.candidateCount)+" candidate region(s)</strong><small>"+esc(shortDate(meta.capturedAt))+" · saved to album</small>";
        $("live-events").prepend(event);
        toast("Potential road-surface candidate saved to the evidence album.");
      }
    } catch(err){console.warn(err);$("analysis-state").textContent="Analysis unavailable";}
    finally{state.analyzingFrame=false;}
  }

  async function handleUpload(file) {
    if(!file)return;
    if(!["image/jpeg","image/png","image/webp"].includes(file.type))return toast("Choose a JPG, PNG or WebP image.");
    if(file.size>12*1024*1024)return toast("Image exceeds the 12 MB upload limit.");
    state.currentUpload=file;
    const preview=$("upload-preview");preview.innerHTML="";
    const img=document.createElement("img");img.src=URL.createObjectURL(file);img.alt="Selected road image";preview.appendChild(img);
    $("analyze-upload").disabled=false;
    $("upload-result").innerHTML='<div class="empty-state"><span>⌕</span><strong>Ready to analyse</strong><p>Press the analysis button to run preprocessing and save metadata.</p></div>';
  }
  async function processUpload() {
    if(!state.currentUpload)return;
    $("analyze-upload").disabled=true;$("upload-result").innerHTML='<div class="empty-state"><span>◌</span><strong>Analysing image…</strong><p>Running the selected processing path.</p></div>';
    try {
      const item=await saveImage(state.currentUpload,state.currentUpload.name,"image-upload");
      const a=item.analysis;
      const imageSrc=imageUrl(item);
      $("upload-result").innerHTML='<span class="tag tag-gold">'+esc(a.method)+'</span><img class="result-image" src="'+imageSrc+'" alt="Processed road image"><div class="analysis-kpis"><div><small>Candidate regions</small><strong>'+esc(a.candidateCount||0)+'</strong></div><div><small>Candidate area</small><strong>'+esc(a.areaPct||0)+'%</strong></div><div><small>Visual index</small><strong>'+esc(a.severity||"Not scored")+'</strong></div><div><small>GPS metadata</small><strong>'+(item.metadata.latitude==null?"Unavailable":"Tagged")+'</strong></div></div><p class="small-note">'+esc(a.disclaimer||"Preliminary visual analysis only.")+'</p><button class="button button-green" id="use-upload-report">Prepare civic report</button>';
      $("use-upload-report").addEventListener("click",()=>{navigate("reports");$("report-record").value=item.id;updateReportPreview();});
      toast("Image and metadata saved to your local evidence album.");
    } catch(err){$("upload-result").textContent="Could not analyse image: "+err.message;}
    finally{$("analyze-upload").disabled=false;}
  }

  async function googleCredentialCallback(response) {
    try {
      const res=await fetch(apiUrl()+"/api/v1/auth/google",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({credential:response.credential})});
      const data=await res.json();
      if(!res.ok)throw new Error(data.error||"Google authentication failed");
      state.session=data.sessionToken;state.user=data.user;sessionStorage.setItem("roadguard-session",data.sessionToken);
      sessionStorage.setItem("roadguard-user",JSON.stringify(data.user));updateUser();toast("Signed in as "+data.user.email);
    } catch(err){toast("Sign-in could not be verified: "+err.message);}
  }
  function updateUser() {
    const signed=!!state.user;
    $("user-name").textContent=signed?(state.user.name||"Google user"):"Local workspace";
    $("user-email").textContent=signed?(state.user.email||"Google account"):"Not signed in";
    $("user-avatar").textContent=signed?(state.user.name||"RG").split(/\s+/).slice(0,2).map(x=>x[0]).join("").toUpperCase():"RG";
    $("session-state").textContent=signed?"Verified Google session":"Local workspace";
  }
  function setupGoogle() {
    const id=CFG.googleClientId||"";
    if(!id){$("oauth-setup").textContent="Google OAuth is not configured. Add your Web Client ID to web/app-config.js and configure the same audience in the Cloudflare Worker.";return;}
    const wait=()=> {
      if(!window.google || !google.accounts || !google.accounts.id)return setTimeout(wait,250);
      google.accounts.id.initialize({client_id:id,callback:googleCredentialCallback,auto_select:false});
      google.accounts.id.renderButton($("google-signin"),{theme:"outline",size:"medium",shape:"pill",text:"signin_with"});
    };
    wait();
  }

  async function sendReport() {
    const item=selectedEvidence(), recipient=$("recipient-email").value.trim();
    if(!item)return toast("Select an evidence image first.");
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient))return toast("Enter a verified municipal office email address.");
    if(!sessionToken())return toast("Sign in with Google before sending a report.");
    if(!confirm("Send this report and the selected image attachment to "+recipient+"?"))return;
    const base=apiUrl();if(!base)return toast("Cloudflare Worker is not configured.");
    try {
      const attachment=await blobToBase64(item.blob);
      const report=buildReportText(item);
      const res=await fetch(base+"/api/v1/reports/email",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+sessionToken()},body:JSON.stringify({
        confirmSend:true,to:recipient,subject:report.subject,text:report.body,
        attachment:{filename:item.metadata.filename,content_base64:attachment,content_type:item.blob.type||"image/jpeg"}
      })});
      const data=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(data.error||"Email service unavailable");
      const saved={id:"rep-"+Date.now(),createdAt:Date.now(),recordId:item.id,recipient:recipient,providerId:data.id||null};
      await dbPut("reports",saved);await refreshData();toast("Report submitted to the configured email service.");
    } catch(err){toast("Email was not sent: "+err.message+". Use Create email draft instead.");}
  }
  function draftReport() {
    const item=selectedEvidence(), recipient=$("recipient-email").value.trim();
    if(!item)return toast("Select an evidence image first.");
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient))return toast("Enter a verified municipal office email address.");
    const r=buildReportText(item);
    const uri="mailto:"+encodeURIComponent(recipient)+"?subject="+encodeURIComponent(r.subject)+"&body="+encodeURIComponent(r.body);
    window.location.href=uri;
    downloadBlob(item.blob,item.metadata.filename);
    toast("Email draft opened. Attach the downloaded evidence image before sending.");
    const rep={id:"rep-"+Date.now(),createdAt:Date.now(),recordId:item.id,recipient:recipient,draft:true};
    dbPut("reports",rep).then(refreshData);
  }
  function downloadReport() {
    const item=selectedEvidence();if(!item)return;
    const r=buildReportText(item);
    const payload={project:"RoadGuard",recipient:r.recipient,subject:r.subject,body:r.body,metadata:item.metadata,analysis:item.analysis};
    downloadBlob(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}),"RoadGuard_report_"+Date.now()+".json");
  }
  async function healthCheck() {
    $("api-status").textContent="Checking Worker…";
    const base=apiUrl();
    if(!base){$("api-status").textContent="Local mode";return;}
    try {
      const res=await fetch(base+"/health");const h=await res.json();
      $("api-status").textContent=res.ok?"Worker "+(h.status||"online"):"Worker error";
      $("worker-health").textContent=res.ok?"Online":"Error";
      $("worker-model").textContent=h.modelConfigured?"Configured":"Not configured";
      $("worker-email").textContent=h.emailConfigured?"Configured":"Not configured";
      $("model-note").textContent=h.modelConfigured?"Trained-model endpoint is configured. Sign in to enable authenticated inference.":"Browser CV baseline is available. A trained road-damage model is not configured.";
    } catch(_){
      $("api-status").textContent="Worker unavailable";
      $("worker-health").textContent="Unavailable";$("worker-model").textContent="Unknown";$("worker-email").textContent="Unknown";
    }
  }
  function navigate(view) {
    document.querySelectorAll(".view").forEach(el=>el.classList.toggle("active",el.id==="view-"+view));
    document.querySelectorAll(".nav-item").forEach(el=>el.classList.toggle("active",el.dataset.view===view));
    const labels={dashboard:"Overview",live:"Live dashcam inspection",upload:"Image inspection",album:"Evidence album",reports:"Reports & civic email",settings:"Settings"};
    $("page-title").textContent=labels[view]||"RoadGuard";
    const sub={dashboard:"ROAD CONDITION MONITORING",live:"CAMERA ACQUISITION",upload:"IMAGE PROCESSING",album:"LOCAL EVIDENCE LIBRARY",reports:"CIVIC COMMUNICATION",settings:"APP CONFIGURATION"};
    $("page-eyebrow").textContent=sub[view]||"ROADGUARD";
    if(view==="album")renderAlbum();
    if(view==="reports"){renderReportOptions();updateReportPreview();}
    if(view==="settings")$("api-url").value=apiUrl();
    window.scrollTo({top:0,behavior:"smooth"});
  }
  function wireEvents() {
    document.querySelectorAll("[data-view]").forEach(btn=>btn.addEventListener("click",()=>navigate(btn.dataset.view)));
    document.querySelectorAll("[data-go]").forEach(btn=>btn.addEventListener("click",()=>navigate(btn.dataset.go)));
    $("start-camera").addEventListener("click",startCamera);
    $("toggle-record").addEventListener("click",toggleRecording);
    $("stop-camera").addEventListener("click",stopCamera);
    $("image-file").addEventListener("change",e=>handleUpload(e.target.files[0]));
    $("analyze-upload").addEventListener("click",processUpload);
    $("clear-upload").addEventListener("click",()=>{state.currentUpload=null;$("image-file").value="";$("upload-preview").innerHTML="<span>Preview will appear here</span>";$("analyze-upload").disabled=true;$("upload-result").innerHTML='<div class="empty-state"><span>⌕</span><strong>Waiting for image</strong><p>Choose a road photo to see preprocessing output and candidate regions.</p></div>';});
    $("album-search").addEventListener("input",renderAlbum);
    $("report-record").addEventListener("change",updateReportPreview);
    ["recipient-email","road-authority","report-contact","report-notes"].forEach(id=>$(id).addEventListener("input",updateReportPreview));
    $("send-report").addEventListener("click",sendReport);
    $("draft-report").addEventListener("click",draftReport);
    $("download-report").addEventListener("click",downloadReport);
    $("save-api").addEventListener("click",()=>{try{const v=new URL($("api-url").value.trim());if(v.protocol!=="https:")throw new Error();localStorage.setItem("roadguard-api",v.origin+v.pathname.replace(/\/$/,""));healthCheck();toast("API endpoint saved.");}catch(_){toast("Enter a valid HTTPS Worker URL.");}});
    $("local-mode").addEventListener("click",()=>toast("Local workspace is active. Evidence remains in this browser."));
    $("signout").addEventListener("click",()=>{state.session=null;state.user=null;sessionStorage.removeItem("roadguard-session");sessionStorage.removeItem("roadguard-user");updateUser();toast("Signed out. Local evidence remains on this device.");});
    $("clear-videos").addEventListener("click",async()=>{if(confirm("Delete both locally stored dashcam clips?")){for(const x of state.videos)await dbDelete("videos",x.id);await refreshData();toast("Saved videos deleted.");}});
    $("clear-all").addEventListener("click",async()=>{if(confirm("Delete all local evidence images, videos and report history? This cannot be undone.")){for(const x of state.records)await dbDelete("images",x.id);for(const x of state.videos)await dbDelete("videos",x.id);for(const x of state.reports)await dbDelete("reports",x.id);await refreshData();toast("Local evidence cleared.");}});
    $("export-data").addEventListener("click",()=>{const data=state.records.map(x=>({metadata:x.metadata,analysis:{method:x.analysis.method,candidateCount:x.analysis.candidateCount,areaPct:x.analysis.areaPct,severity:x.analysis.severity}}));downloadBlob(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}),"RoadGuard_metadata_export.json");});
    $("install-app").addEventListener("click",async()=>{if(state.installPrompt){state.installPrompt.prompt();await state.installPrompt.userChoice;state.installPrompt=null;$("install-app").hidden=true;}else toast("Use your browser menu and choose Install app / Add to Home Screen.");});
    $("clock-hud").textContent=new Date().toLocaleTimeString();
    setInterval(()=>$("clock-hud").textContent=new Date().toLocaleTimeString(),1000);
    $("report-record").addEventListener("change",updateReportPreview);
    $("last-sync").textContent="Local device storage · "+(navigator.storage&&navigator.storage.estimate?"quota-aware":"browser-managed");
  }

  async function init() {
    wireEvents();
    try { state.db=await openDB(); await refreshData(); }
    catch(err){toast("Local storage could not be opened: "+err.message);}
    const savedUser=sessionStorage.getItem("roadguard-user");
    if(savedUser){try{state.user=JSON.parse(savedUser);state.session=sessionStorage.getItem("roadguard-session");}catch(_){}}
    updateUser();setupGoogle();healthCheck();
    if("serviceWorker" in navigator)navigator.serviceWorker.register("./sw.js").catch(()=>{});
    window.addEventListener("beforeinstallprompt",event=>{event.preventDefault();state.installPrompt=event;$("install-app").hidden=false;});
    window.addEventListener("appinstalled",()=>toast("RoadGuard installed on this device."));
    if(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia) {
      state.frameTimer=setInterval(analyzeLiveFrame,5000);
    }
  }
  document.addEventListener("DOMContentLoaded",init);
})();