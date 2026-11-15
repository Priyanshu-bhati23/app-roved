/*
 * The hero's interactive 3D phone (three.js r128).
 *
 * Drag to spin, move the pointer to tilt. Check labels orbit the phone. While a build is
 * scanned a laser sweeps the device and the screen shows progress; the result lands on the
 * screen and each label turns green or red. Exposes window.Phone3D = {idle, scanning, result}.
 * Fails silently (the page works without it) when WebGL is unavailable.
 */
(function () {
  "use strict";
  const canvas = document.getElementById("phone3d");
  const stage = document.getElementById("stage");
  const chipLayer = document.getElementById("chips");
  const noop = { idle() {}, scanning() {}, result() {} };
  window.Phone3D = noop;
  const off = () => document.documentElement.classList.add("no-3d");
  if (!canvas || !window.THREE) return off();
  const THREE = window.THREE;
  const reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch (e) {
    return off();
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputEncoding = THREE.sRGBEncoding;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0, 0, 9.2);

  // ---------- lights ----------
  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(3, 4, 6);
  scene.add(key);
  const rimA = new THREE.PointLight(0x5fd4ff, 2.2, 14);
  rimA.position.set(-4, 1.5, 2);
  scene.add(rimA);
  const rimB = new THREE.PointLight(0x9b6bff, 2.0, 14);
  rimB.position.set(4, -2, 1.5);
  scene.add(rimB);

  // ---------- phone body ----------
  const W = 1.62, H = 3.32, R = 0.27, DEPTH = 0.12, BEVEL = 0.05;
  function roundedRect(w, h, r) {
    const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
    s.moveTo(x + r, y);
    s.lineTo(x + w - r, y);
    s.quadraticCurveTo(x + w, y, x + w, y + r);
    s.lineTo(x + w, y + h - r);
    s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    s.lineTo(x + r, y + h);
    s.quadraticCurveTo(x, y + h, x, y + h - r);
    s.lineTo(x, y + r);
    s.quadraticCurveTo(x, y, x + r, y);
    return s;
  }
  const bodyGeo = new THREE.ExtrudeGeometry(roundedRect(W, H, R), {
    depth: DEPTH, bevelEnabled: true, bevelThickness: BEVEL, bevelSize: BEVEL, bevelSegments: 8, curveSegments: 32,
  });
  bodyGeo.center();
  const glass = new THREE.MeshStandardMaterial({ color: 0x0a0c14, metalness: 0.4, roughness: 0.18 });
  const frameMat = new THREE.MeshStandardMaterial({ color: 0xb9c0d0, metalness: 0.95, roughness: 0.26 });
  const phone = new THREE.Group();
  const body = new THREE.Mesh(bodyGeo, [glass, frameMat]);
  phone.add(body);
  const FRONT = DEPTH / 2 + BEVEL + 0.002;

  // back panel tint + camera bump
  const backMat = new THREE.MeshStandardMaterial({ color: 0x1c2238, metalness: 0.55, roughness: 0.35 });
  const back = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(W - 0.02, H - 0.02, R), 32), backMat);
  back.position.z = -FRONT;
  back.rotation.y = Math.PI;
  phone.add(back);
  const bumpGeo = new THREE.ExtrudeGeometry(roundedRect(0.72, 0.72, 0.17), {
    depth: 0.04, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.02, bevelSegments: 4, curveSegments: 16,
  });
  bumpGeo.center();
  const bump = new THREE.Mesh(bumpGeo, [backMat, frameMat]);
  bump.position.set(W / 2 - 0.5, H / 2 - 0.5, -FRONT - 0.03);
  phone.add(bump);
  const lensMat = new THREE.MeshStandardMaterial({ color: 0x05060a, metalness: 0.9, roughness: 0.1 });
  const ringMat = new THREE.MeshStandardMaterial({ color: 0x8a92a6, metalness: 1, roughness: 0.3 });
  [[-0.15, 0.15], [-0.15, -0.15], [0.16, 0]].forEach(([x, y]) => {
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.115, 0.115, 0.05, 32), ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.set(bump.position.x + x, bump.position.y + y, bump.position.z - 0.04);
    phone.add(ring);
    const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.052, 32), lensMat);
    lens.rotation.x = Math.PI / 2;
    lens.position.copy(ring.position);
    lens.position.z -= 0.002;
    phone.add(lens);
  });
  // side buttons
  const btnGeo = new THREE.BoxGeometry(0.04, 0.32, 0.06);
  [[-W / 2 - 0.05, 0.75], [-W / 2 - 0.05, 0.3], [W / 2 + 0.05, 0.5]].forEach(([x, y]) => {
    const b = new THREE.Mesh(btnGeo, frameMat);
    b.position.set(x, y, 0);
    phone.add(b);
  });

  // ---------- screen ----------
  const SW = W - 0.12, SH = H - 0.12;
  const tex = document.createElement("canvas");
  tex.width = 640;
  tex.height = Math.round(640 * (SH / SW));
  const ctx = tex.getContext("2d");
  const screenTex = new THREE.CanvasTexture(tex);
  screenTex.encoding = THREE.sRGBEncoding;
  screenTex.anisotropy = 4;
  const screenGeo = new THREE.ShapeGeometry(roundedRect(SW, SH, R - 0.05), 32);
  const uv = screenGeo.attributes.uv, pos = screenGeo.attributes.position;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, (pos.getX(i) + SW / 2) / SW, (pos.getY(i) + SH / 2) / SH);
  const screen = new THREE.Mesh(screenGeo, new THREE.MeshBasicMaterial({ map: screenTex, toneMapped: false }));
  screen.position.z = FRONT;
  phone.add(screen);
  // glass reflection: a soft diagonal band that slides across the screen as the phone turns
  const sheenTex = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const g = c.getContext("2d");
    const gr = g.createLinearGradient(0, 0, 256, 256);
    gr.addColorStop(0.0, "rgba(255,255,255,0)");
    gr.addColorStop(0.42, "rgba(255,255,255,0)");
    gr.addColorStop(0.5, "rgba(255,255,255,0.13)");
    gr.addColorStop(0.58, "rgba(255,255,255,0)");
    gr.addColorStop(1.0, "rgba(255,255,255,0)");
    g.fillStyle = gr;
    g.fillRect(0, 0, 256, 256);
    const t = new THREE.CanvasTexture(c);
    t.wrapS = THREE.RepeatWrapping;
    return t;
  })();
  const sheenGeo = new THREE.ShapeGeometry(roundedRect(SW, SH, R - 0.05), 32);
  const suv = sheenGeo.attributes.uv, spos = sheenGeo.attributes.position;
  for (let i = 0; i < suv.count; i++) suv.setXY(i, (spos.getX(i) + SW / 2) / SW, (spos.getY(i) + SH / 2) / SH);
  const sheen = new THREE.Mesh(sheenGeo,
    new THREE.MeshBasicMaterial({ map: sheenTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  sheen.position.z = FRONT + 0.004;
  phone.add(sheen);

  // laser sweep
  const laserMat = new THREE.MeshBasicMaterial({ color: 0x5fd4ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
  const laser = new THREE.Mesh(new THREE.PlaneGeometry(W + 0.9, 0.035), laserMat);
  const glowTex = (() => {
    const c = document.createElement("canvas");
    c.width = 256; c.height = 64;
    const g = c.getContext("2d");
    const v = g.createLinearGradient(0, 0, 0, 64);
    v.addColorStop(0, "rgba(255,255,255,0)"); v.addColorStop(0.5, "rgba(255,255,255,1)"); v.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = v; g.fillRect(0, 0, 256, 64);
    g.globalCompositeOperation = "destination-in";
    const h = g.createLinearGradient(0, 0, 256, 0);
    h.addColorStop(0, "rgba(0,0,0,0)"); h.addColorStop(0.15, "rgba(0,0,0,1)"); h.addColorStop(0.85, "rgba(0,0,0,1)"); h.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = h; g.fillRect(0, 0, 256, 64);
    return new THREE.CanvasTexture(c);
  })();
  const glowMat = new THREE.MeshBasicMaterial({ map: glowTex, color: 0x5fd4ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
  const laserGlow = new THREE.Mesh(new THREE.PlaneGeometry(W + 0.6, 0.38), glowMat);
  laser.position.z = laserGlow.position.z = FRONT + 0.03;
  phone.add(laserGlow);
  phone.add(laser);
  scene.add(phone);

  // ---------- particles ----------
  const N = window.innerWidth < 700 ? 260 : 650;
  const pGeo = new THREE.BufferGeometry(), pPos = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    const r = 3 + Math.random() * 6, a = Math.random() * Math.PI * 2;
    pPos[i * 3] = Math.cos(a) * r;
    pPos[i * 3 + 1] = (Math.random() - 0.5) * 9;
    pPos[i * 3 + 2] = Math.sin(a) * r - 4;
  }
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  const dot = (() => {
    const c = document.createElement("canvas"); c.width = c.height = 32;
    const g = c.getContext("2d"), gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
    gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr; g.fillRect(0, 0, 32, 32);
    return new THREE.CanvasTexture(c);
  })();
  const pMat = new THREE.PointsMaterial({ size: 0.07, map: dot, color: 0x7fd8ff, transparent: true, opacity: 0.7, depthWrite: false, blending: THREE.AdditiveBlending });
  const particles = new THREE.Points(pGeo, pMat);
  scene.add(particles);

  // ---------- screen drawing ----------
  const S = tex.width / SW; // px per world unit
  const TW = tex.width, TH = tex.height;
  const ICONS = [["#ff6b6b", "#ff9a5a"], ["#4fe3a1", "#24b47e"], ["#5fd4ff", "#3b82f6"], ["#ffd166", "#ff9f1c"], ["#b388ff", "#7c4dff"],
    ["#ff8fab", "#f72585"], ["#64dfdf", "#0096c7"], ["#f4f1de", "#c9c5b9"], ["#9ef01a", "#38b000"], ["#ffafcc", "#cdb4db"],
    ["#a0c4ff", "#4361ee"], ["#ffcad4", "#f08080"], ["#90e0ef", "#00b4d8"], ["#e9c46a", "#e76f51"], ["#cdb4db", "#9d4edd"], ["#adb5bd", "#495057"]];
  function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function wallpaper(top, bottom) {
    const g = ctx.createLinearGradient(0, 0, TW, TH);
    g.addColorStop(0, top); g.addColorStop(1, bottom);
    ctx.fillStyle = g; ctx.fillRect(0, 0, TW, TH);
    const b = ctx.createRadialGradient(TW * 0.8, TH * 0.15, 0, TW * 0.8, TH * 0.15, TW);
    b.addColorStop(0, "rgba(95,212,255,0.35)"); b.addColorStop(1, "rgba(95,212,255,0)");
    ctx.fillStyle = b; ctx.fillRect(0, 0, TW, TH);
  }
  function chrome(dark) {
    ctx.fillStyle = "#000"; rr(TW / 2 - 95, 26, 190, 54, 27); ctx.fill(); // the camera pill
    ctx.fillStyle = dark ? "#fff" : "#fff";
    ctx.font = "600 34px Inter Tight, system-ui, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText("10:08", 62, 54);
    ctx.textAlign = "right"; ctx.fillText("●●●", TW - 56, 54);
  }
  function icon(x, y, s, colors, label) {
    const g = ctx.createLinearGradient(x, y, x + s, y + s);
    g.addColorStop(0, colors[0]); g.addColorStop(1, colors[1]);
    ctx.fillStyle = g; rr(x, y, s, s, s * 0.24); ctx.fill();
    if (label) {
      ctx.fillStyle = "rgba(255,255,255,0.92)"; ctx.font = "500 21px Inter Tight, system-ui, sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText(label, x + s / 2, y + s + 10);
    }
  }
  const LABELS = ["Notes", "Fit", "Weather", "Photos", "Music", "Chat", "Maps", "Docs", "Health", "Shop", "Mail", "Clock", "Files", "Wallet", "Books", "Tools"];
  function drawHome() {
    wallpaper("#141a3a", "#04050c");
    chrome();
    // widget
    ctx.fillStyle = "rgba(255,255,255,0.10)"; rr(48, 130, TW - 96, 240, 40); ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = "#5fd4ff"; ctx.font = "600 24px JetBrains Mono, monospace"; ctx.textAlign = "left"; ctx.textBaseline = "top";
    ctx.fillText("APP-ROVED", 84, 162);
    ctx.fillStyle = "#fff"; ctx.font = "700 46px Inter Tight, system-ui, sans-serif";
    ctx.fillText("Ready for", 84, 206); ctx.fillText("App Review?", 84, 258);
    ctx.fillStyle = "rgba(255,255,255,0.65)"; ctx.font = "500 24px Inter Tight, system-ui, sans-serif";
    ctx.fillText("Drop your .ipa to check", 84, 322);
    const s = 108, gap = (TW - 4 * s) / 5;
    for (let i = 0; i < 16; i++) {
      const c = i % 4, r = Math.floor(i / 4);
      icon(gap + c * (s + gap), 430 + r * (s + 64), s, ICONS[i], LABELS[i]);
    }
    ctx.fillStyle = "rgba(255,255,255,0.14)"; rr(36, TH - 200, TW - 72, 156, 52); ctx.fill();
    for (let i = 0; i < 4; i++) icon(gap + i * (s + gap), TH - 176, s, ICONS[(i * 5) % 16]);
    ctx.fillStyle = "rgba(255,255,255,0.6)"; rr(TW / 2 - 100, TH - 26, 200, 9, 5); ctx.fill();
    screenTex.needsUpdate = true;
  }
  const CHECKS = ["Info.plist keys", "Purpose strings", "Privacy manifest", "Required-reason APIs", "Private frameworks", "UIWebView", "Architectures", "Code signature", "Entitlements", "SDK version"];
  function drawScanning(name, p) {
    wallpaper("#07131f", "#020308");
    chrome();
    ctx.textAlign = "left"; ctx.textBaseline = "top";
    ctx.fillStyle = "#5fd4ff"; ctx.font = "600 24px JetBrains Mono, monospace"; ctx.fillText("SCANNING", 60, 140);
    ctx.fillStyle = "#fff"; ctx.font = "700 44px Inter Tight, system-ui, sans-serif";
    ctx.fillText(name.length > 18 ? name.slice(0, 17) + "…" : name, 60, 180);
    ctx.fillStyle = "rgba(255,255,255,0.12)"; rr(60, 260, TW - 120, 14, 7); ctx.fill();
    ctx.fillStyle = "#5fd4ff"; rr(60, 260, Math.max(14, (TW - 120) * p), 14, 7); ctx.fill();
    const done = Math.floor(p * CHECKS.length);
    CHECKS.forEach((c, i) => {
      const y = 330 + i * 92;
      ctx.fillStyle = i < done ? "rgba(79,227,161,0.14)" : "rgba(255,255,255,0.06)"; rr(60, y, TW - 120, 72, 20); ctx.fill();
      ctx.fillStyle = i < done ? "#4fe3a1" : i === done ? "#5fd4ff" : "rgba(255,255,255,0.35)";
      ctx.font = "600 30px Inter Tight, system-ui, sans-serif"; ctx.textBaseline = "middle";
      ctx.fillText(i < done ? "✓" : i === done ? "◌" : "·", 88, y + 36);
      ctx.fillStyle = i <= done ? "#fff" : "rgba(255,255,255,0.45)"; ctx.font = "500 28px Inter Tight, system-ui, sans-serif";
      ctx.fillText(c, 136, y + 36); ctx.textBaseline = "top";
    });
    screenTex.needsUpdate = true;
  }
  const VERDICT = { blocked: ["#ff5d73", "BLOCKED"], needs_review: ["#ffb547", "NEEDS REVIEW"], clear: ["#4fe3a1", "CLEAR"] };
  function drawResult(d) {
    const [color, word] = VERDICT[d.verdict] || VERDICT.needs_review;
    wallpaper("#0c0f1e", "#020308");
    chrome();
    const g = ctx.createRadialGradient(TW / 2, 330, 0, TW / 2, 330, 360);
    g.addColorStop(0, color + "55"); g.addColorStop(1, color + "00");
    ctx.fillStyle = g; ctx.fillRect(0, 100, TW, 520);
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.strokeStyle = color; ctx.lineWidth = 12; ctx.beginPath(); ctx.arc(TW / 2, 300, 104, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = color; ctx.font = "800 120px Inter Tight, system-ui, sans-serif";
    ctx.fillText(d.verdict === "clear" ? "✓" : String(d.counts.blocker || d.counts.warning), TW / 2, 306);
    ctx.font = "800 54px Inter Tight, system-ui, sans-serif"; ctx.fillText(word, TW / 2, 470);
    ctx.fillStyle = "rgba(255,255,255,0.7)"; ctx.font = "500 28px Inter Tight, system-ui, sans-serif";
    ctx.fillText(d.counts.blocker + " blockers · " + d.counts.warning + " warnings · " + d.counts.info + " info", TW / 2, 530);
    ctx.textAlign = "left";
    const seen = new Set();
    const items = d.findings.filter(f => !seen.has(f.signal.id) && seen.add(f.signal.id)).slice(0, 6);
    items.forEach((f, i) => {
      const y = 600 + i * 104, c = f.signal.severity === "blocker" ? "#ff5d73" : f.signal.severity === "warning" ? "#ffb547" : "#8f9bd6";
      ctx.fillStyle = "rgba(255,255,255,0.06)"; rr(52, y, TW - 104, 88, 22); ctx.fill();
      ctx.fillStyle = c; rr(52, y, 10, 88, 5); ctx.fill();
      ctx.fillStyle = c; ctx.font = "600 20px JetBrains Mono, monospace"; ctx.textBaseline = "top"; ctx.fillText(f.signal.id, 82, y + 14);
      ctx.fillStyle = "#fff"; ctx.font = "500 26px Inter Tight, system-ui, sans-serif";
      let t = f.signal.title; while (ctx.measureText(t).width > TW - 160 && t.length > 4) t = t.slice(0, -2);
      ctx.fillText(t === f.signal.title ? t : t + "…", 82, y + 44);
    });
    if (!items.length) {
      ctx.fillStyle = "rgba(255,255,255,0.75)"; ctx.font = "500 30px Inter Tight, system-ui, sans-serif"; ctx.textAlign = "center";
      ctx.fillText("No build problems found", TW / 2, 660);
    }
    screenTex.needsUpdate = true;
  }

  // ---------- orbiting check labels ----------
  const CHIPS = [["Info.plist", ["PLIST-001", "PLIST-002", "PLIST-003", "PLIST-004", "PLIST-005", "PLIST-008"]], ["Privacy manifest", ["PRIV-"]],
    ["Code signing", ["SIGN-"]], ["Binary", ["MACHO-"]], ["SDK version", ["PLIST-006", "PLIST-007"]], ["Review risks", ["REVIEW-"]]];
  const chips = CHIPS.map(([label, ids], i) => {
    const el = document.createElement("div");
    el.className = "chip";
    el.innerHTML = '<i></i><span>' + label + "</span>";
    chipLayer.appendChild(el);
    return { el, ids, angle: (i / CHIPS.length) * Math.PI * 2, y: [1.15, 0.35, -0.45, 1.25, -1.1, 0.1][i] };
  });
  function setChips(state, d) {
    chips.forEach((c, i) => {
      c.el.classList.remove("ok", "bad", "checking");
      if (state === "scanning") setTimeout(() => c.el.classList.add("checking"), i * 140);
      if (state === "result") {
        const hit = d.findings.some(f => f.signal.severity !== "info" && c.ids.some(id => f.signal.id.startsWith(id)));
        setTimeout(() => c.el.classList.add(hit ? "bad" : "ok"), i * 120);
      }
    });
  }

  // ---------- interaction ----------
  let px = 0, py = 0, yaw = 0, yawVel = 0, dragging = false, lastX = 0, spin = 0;
  const hint = document.getElementById("stage-hint");
  stage.addEventListener("pointermove", e => {
    const r = stage.getBoundingClientRect();
    px = ((e.clientX - r.left) / r.width) * 2 - 1;
    py = ((e.clientY - r.top) / r.height) * 2 - 1;
    if (dragging) { yawVel = (e.clientX - lastX) * 0.012; yaw += yawVel; lastX = e.clientX; }
  });
  stage.addEventListener("pointerdown", e => { dragging = true; lastX = e.clientX; stage.setPointerCapture(e.pointerId); if (hint) hint.style.opacity = 0; });
  const up = () => { dragging = false; };
  stage.addEventListener("pointerup", up);
  stage.addEventListener("pointercancel", up);
  stage.addEventListener("pointerleave", () => { if (!dragging) { px = 0; py = 0; } });

  function resize() {
    const w = stage.clientWidth, h = stage.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.position.z = w < 520 ? 8.7 : 7.6;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);
  resize();

  let visible = true;
  if ("IntersectionObserver" in window) new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(stage);

  // ---------- state ----------
  let mode = "idle", scanStart = 0, scanName = "", lastDraw = 0;
  drawHome();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (mode === "idle") drawHome(); });

  const v = new THREE.Vector3();
  const clock = new THREE.Clock();
  function frame() {
    requestAnimationFrame(frame);
    if (!visible) return;
    const t = clock.getElapsedTime();
    const m = reduced ? 0 : 1;
    if (!dragging) { yawVel *= 0.94; yaw += yawVel; yaw *= 0.985; }
    spin *= 0.92;
    const targetY = yaw + px * 0.45 + m * Math.sin(t * 0.5) * 0.18 + spin;
    const targetX = py * 0.28 + m * Math.sin(t * 0.7) * 0.05;
    phone.rotation.y += (targetY - 0.32 - phone.rotation.y) * 0.08;
    phone.rotation.x += (targetX - phone.rotation.x) * 0.08;
    phone.position.y = m * Math.sin(t * 1.1) * 0.07;
    sheenTex.offset.x = phone.rotation.y * 0.55 + phone.rotation.x * 0.3;
    particles.rotation.y = t * 0.03 * m + px * 0.05;
    particles.position.y = -py * 0.1;

    if (mode === "scanning") {
      const p = Math.min(0.94, (t - scanStart) / 9);
      const sweep = Math.sin((t - scanStart) * 2.4);
      laser.position.y = laserGlow.position.y = sweep * (H / 2 + 0.05);
      laserMat.opacity = 0.95; glowMat.opacity = 0.55;
      if (t - lastDraw > 0.12) { drawScanning(scanName, p); lastDraw = t; }
    } else {
      laserMat.opacity *= 0.9; glowMat.opacity *= 0.9;
    }

    // chips orbit the phone and fade behind it
    const rect = stage.getBoundingClientRect();
    const radius = rect.width < 520 ? 1.22 : 1.75;
    chips.forEach((c, i) => {
      const a = c.angle + t * 0.25 * (m || 0.001) + phone.rotation.y * 0.3;
      v.set(Math.cos(a) * radius, c.y + phone.position.y, Math.sin(a) * radius * 0.75);
      const depth = v.z;
      v.project(camera);
      const x = (v.x * 0.5 + 0.5) * rect.width, y = (-v.y * 0.5 + 0.5) * rect.height;
      const front = depth > -0.2;
      c.el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(-50%,-50%) scale(" + (0.82 + (depth + 1.5) * 0.08).toFixed(3) + ")";
      c.el.style.opacity = front ? 1 : 0.28;
      c.el.style.zIndex = front ? 3 : 1;
    });
    renderer.render(scene, camera);
  }
  frame();

  window.Phone3D = {
    idle() { mode = "idle"; drawHome(); setChips("idle"); },
    scanning(name) { mode = "scanning"; scanName = name || "Your build"; scanStart = clock.getElapsedTime(); lastDraw = 0; setChips("scanning"); },
    result(d) { mode = "result"; drawResult(d); setChips("result", d); if (!reduced) spin = Math.PI * 2; yaw = 0; },
  };
})();
