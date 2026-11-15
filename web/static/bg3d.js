/*
 * The interactive 3D background: glossy app icons floating in depth (one InstancedMesh, so one
 * draw call). The pointer carries a light that brightens nearby icons and pushes them aside;
 * a click or tap on empty space sends a shockwave through the field; scrolling moves the camera
 * through it. Sets window.__bg3d = true when it runs, so site3d.js skips its CSS fallback.
 */
(function () {
  "use strict";
  const host = document.getElementById("bg3d");
  if (!host || !window.THREE) return;
  const THREE = window.THREE;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mobile = matchMedia("(pointer: coarse)").matches || innerWidth < 700;

  const canvas = document.createElement("canvas");
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: !mobile, alpha: false, powerPreference: "low-power" });
  } catch (e) {
    return;
  }
  host.appendChild(canvas);
  host.classList.add("gl");
  window.__bg3d = true;
  // quality steps: drop resolution if the device can't keep up (it's a background, softness is fine)
  const RATIOS = (mobile ? [1, 0.75, 0.55] : [1.5, 1, 0.7, 0.5]).map(r => Math.min(r, devicePixelRatio || 1));
  let level = 0, frames = 0, windowStart = performance.now(), skip = 1, tick = 0;
  renderer.setPixelRatio(RATIOS[0]);
  renderer.setClearColor(0x07080f, 1);
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x07080f, 10, 34);
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 60);

  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const sun = new THREE.DirectionalLight(0xffffff, 0.55);
  sun.position.set(3, 5, 6);
  scene.add(sun);
  const torch = new THREE.PointLight(0x7fe0ff, 0, 18, 1.2); // follows the pointer
  scene.add(torch);
  const flash = new THREE.PointLight(0xb388ff, 0, 18, 1.4); // lights up a shockwave
  scene.add(flash);

  // ---------- one rounded "app icon" shape, instanced ----------
  const s = 0.5, r = 0.16, shape = new THREE.Shape();
  shape.moveTo(-s + r, -s); shape.lineTo(s - r, -s); shape.quadraticCurveTo(s, -s, s, -s + r);
  shape.lineTo(s, s - r); shape.quadraticCurveTo(s, s, s - r, s); shape.lineTo(-s + r, s);
  shape.quadraticCurveTo(-s, s, -s, s - r); shape.lineTo(-s, -s + r); shape.quadraticCurveTo(-s, -s, -s + r, -s);
  const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.18, bevelEnabled: true, bevelThickness: 0.07, bevelSize: 0.07, bevelSegments: 3, curveSegments: 8 });
  geo.center();
  const mat = new THREE.MeshPhongMaterial({ color: 0xffffff, shininess: 90, specular: 0x6f7fa0 });
  const COUNT = mobile ? 26 : 46;
  const mesh = new THREE.InstancedMesh(geo, mat, COUNT);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(mesh);

  const PALETTE = [0x5fd4ff, 0x3b82f6, 0x9b6bff, 0x4fe3a1, 0xffb547, 0xff6b8b, 0x7fe0ff, 0x6d5dfc];
  const SPAN = 26; // vertical size of the field before it repeats
  const icons = [];
  for (let i = 0; i < COUNT; i++) {
    const z = -8 - Math.random() * 20;
    const base = new THREE.Color(PALETTE[i % PALETTE.length]).multiplyScalar(0.75);
    icons.push({
      // fraction of the visible width at its depth; most icons sit toward the sides so text stays clear
      x: Math.random() < 0.75 ? (Math.random() < 0.5 ? -1 : 1) * (0.42 + Math.random() * 0.62) : (Math.random() - 0.5) * 2,
      y: Math.random() * SPAN,
      z,
      size: 0.55 + Math.random() * 0.75,
      rx: Math.random() * 6.3, ry: Math.random() * 6.3, rz: Math.random() * 6.3,
      vrx: (Math.random() - 0.5) * 0.25, vry: (Math.random() - 0.5) * 0.35,
      bob: Math.random() * 6.3,
      off: new THREE.Vector3(), vel: new THREE.Vector3(), spin: 0,
      base, glow: 0, dim: 0,
    });
    mesh.setColorAt(i, base);
  }

  // ---------- input ----------
  const pointer = { x: 0, y: 0, nx: 0, ny: 0, on: false };
  const waves = [];
  let offTimer = 0;
  function aim(x, y) {
    pointer.x = x; pointer.y = y;
    pointer.nx = (x / innerWidth) * 2 - 1; pointer.ny = -(y / innerHeight) * 2 + 1;
    pointer.on = true;
    clearTimeout(offTimer);
  }
  addEventListener("pointermove", e => aim(e.clientX, e.clientY), { passive: true });
  document.addEventListener("pointerleave", () => { pointer.on = false; });
  // phones: a finger moving across the screen (also while scrolling) pushes icons and carries the light
  addEventListener("touchstart", e => { const t = e.touches[0]; if (t) aim(t.clientX, t.clientY); }, { passive: true });
  addEventListener("touchmove", e => { const t = e.touches[0]; if (t) aim(t.clientX, t.clientY); }, { passive: true });
  addEventListener("touchend", () => { offTimer = setTimeout(() => { pointer.on = false; }, 700); }, { passive: true });
  // a click or tap anywhere that isn't a control sends a shockwave (scrolling doesn't fire click)
  const CONTROLS = "a,button,input,textarea,select,summary,dialog,.stage,#rovy,.yn";
  document.addEventListener("click", e => {
    if (e.target.closest && e.target.closest(CONTROLS)) return;
    if (window.getSelection && String(getSelection()).length) return;
    wave(e.clientX, e.clientY);
  });
  function wave(x, y) {
    waves.push({ x, y, t: performance.now() });
    if (waves.length > 4) waves.shift();
    flash.intensity = 7;
    const ring = document.createElement("i");
    ring.className = "ripple";
    ring.style.left = x + "px"; ring.style.top = y + "px";
    document.body.appendChild(ring);
    setTimeout(() => ring.remove(), 1100);
  }
  // scrolling makes the field spin, faster scrolls spin it harder
  let lastScroll = scrollY, scrollKick = 0;
  addEventListener("scroll", () => { scrollKick = Math.min(6, scrollKick + Math.abs(scrollY - lastScroll) * 0.012); lastScroll = scrollY; }, { passive: true });

  function resize() {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize);
  resize();

  // ---------- keep text readable ----------
  // Icons that drift behind text fade toward the background and shrink. Text boxes are re-measured
  // every few frames (cheap: only elements on screen are kept).
  // Phones are mostly text edge to edge, so there only headlines dim, and less, to keep the field alive.
  const TEXT = mobile ? "h1,h2,.kicker,.price" : "h1,h2,h3,h4,p,li,summary,label,.kicker,.price,.per,.pr,.lede,.sub,.btn,.drop,.vcard,.th-checks";
  const DIM = mobile ? 0.55 : 0.82;
  let textEls = [], rects = [], measuredAt = -1;
  function collectText() { textEls = [...document.querySelectorAll(TEXT)]; }
  collectText();
  setTimeout(collectText, 1500);
  new MutationObserver(() => { clearTimeout(collectText.t); collectText.t = setTimeout(collectText, 300); }).observe(document.body, { childList: true, subtree: true });
  function measure() {
    rects = [];
    for (const el of textEls) {
      const r = el.getBoundingClientRect();
      if (r.width && r.height && r.bottom > 0 && r.top < innerHeight) rects.push(r);
    }
  }
  function behindText(x, y, pad) {
    for (const r of rects) if (x > r.left - pad && x < r.right + pad && y > r.top - pad && y < r.bottom + pad) return true;
    return false;
  }

  // ---------- loop ----------
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e3 = new THREE.Euler(), pos = new THREE.Vector3(), sc = new THREE.Vector3(), v = new THREE.Vector3();
  const tint = new THREE.Color(), white = new THREE.Color(0xdff6ff);
  const halfH = d => Math.tan((camera.fov * Math.PI) / 360) * d;
  let last = performance.now(), camY = 0, stillFrames = 0;

  function frame(now) {
    requestAnimationFrame(frame);
    if (document.hidden) return;
    if (++tick % skip) return; // very slow devices: update the background less often
    const dt = Math.min(0.05 * skip, (now - last) / 1000);
    last = now;
    const t = now / 1000, m = reduced ? 0 : 1;

    // scroll moves the camera down through the field; the pointer leans it a little
    const targetY = -scrollY * 0.0065;
    camY += (targetY - camY) * (reduced ? 1 : 0.12);
    camera.position.set(pointer.nx * 0.6 * m, camY + pointer.ny * 0.4 * m, 0);
    camera.lookAt(pointer.nx * 0.3 * m, camY, -10);

    // torch follows the pointer at a mid depth
    v.set(pointer.nx, pointer.ny, 0.5).unproject(camera).sub(camera.position).normalize();
    torch.position.copy(camera.position).addScaledVector(v, 9);
    torch.intensity += ((pointer.on ? 5 : 0) - torch.intensity) * 0.1;
    flash.intensity *= 0.93;
    if (waves.length) {
      const w = waves[waves.length - 1];
      v.set((w.x / innerWidth) * 2 - 1, -(w.y / innerHeight) * 2 + 1, 0.5).unproject(camera).sub(camera.position).normalize();
      flash.position.copy(camera.position).addScaledVector(v, 10);
    }

    if (tick - measuredAt >= 8 || tick < measuredAt) { measure(); measuredAt = tick; }
    const aspect = camera.aspect;
    for (let i = 0; i < COUNT; i++) {
      const k = icons[i];
      const depth = -k.z, hh = halfH(depth);
      // wrap vertically around the camera so the field never runs out
      let wy = k.y - SPAN / 2;
      wy = ((wy - camY + SPAN / 2) % SPAN + SPAN) % SPAN - SPAN / 2 + camY;
      pos.set(k.x * hh * aspect * 1.15, wy + m * Math.sin(t * 0.6 + k.bob) * 0.25, k.z);

      // where is it on screen?
      v.copy(pos).add(k.off).project(camera);
      const sx = (v.x * 0.5 + 0.5) * innerWidth, sy = (-v.y * 0.5 + 0.5) * innerHeight;

      // pointer: push away and glow
      let near = 0;
      if (pointer.on && m) {
        const dx = sx - pointer.x, dy = sy - pointer.y, d = Math.hypot(dx, dy), R = mobile ? 190 : 260;
        if (d < R) {
          near = 1 - d / R;
          const f = near * near * 1.7 * (depth / 12);
          k.vel.x += (dx / (d || 1)) * f * dt * 9;
          k.vel.y -= (dy / (d || 1)) * f * dt * 9;
          k.spin += near * dt * 2.2;
        }
      }
      // shockwaves: a ring that expands from the click and kicks icons as it passes
      for (const w of waves) {
        const age = (now - w.t) / 1000, radius = age * 900;
        if (age > 1.6) continue;
        const dx = sx - w.x, dy = sy - w.y, d = Math.hypot(dx, dy);
        if (Math.abs(d - radius) < 110) {
          const f = (1 - age / 1.6) * 0.9 * (depth / 12);
          k.vel.x += (dx / (d || 1)) * f;
          k.vel.y -= (dy / (d || 1)) * f;
          k.vel.z += f * 0.8;
          k.spin += 1.2 * (1 - age / 1.6);
          k.glow = Math.max(k.glow, 1 - age / 1.6);
        }
      }
      // springs back home
      k.vel.addScaledVector(k.off, -dt * 3.2);
      k.vel.multiplyScalar(Math.pow(0.04, dt));
      k.off.addScaledVector(k.vel, dt * 3);

      k.rx += (k.vrx * m + k.spin * 0.6 + scrollKick * 0.5 * k.vrx * 8) * dt;
      k.ry += (k.vry * m + k.spin + scrollKick * (k.vry > 0 ? 1 : -1)) * dt;
      k.spin *= Math.pow(0.25, dt);
      k.glow = Math.max(k.glow * Math.pow(0.2, dt), near * 0.85);
      // roughly the icon's on-screen radius, so a corner poking under a word counts too
      const px = (k.size * 0.6 * innerHeight) / (2 * hh);
      const covered = behindText(sx, sy, px) ? 1 : 0;
      k.dim += (covered - k.dim) * Math.min(1, dt * 5);

      // the whole field leans toward the pointer
      e3.set(k.rx - pointer.ny * 0.6 * m, k.ry + pointer.nx * 0.8 * m, k.rz);
      q.setFromEuler(e3);
      sc.setScalar(k.size * (1 + k.glow * 0.18) * (1 - k.dim * DIM * 0.4));
      m4.compose(pos.add(k.off), q, sc);
      mesh.setMatrixAt(i, m4);
      tint.copy(k.base).lerp(white, k.glow * 0.7 * (1 - k.dim * DIM)).multiplyScalar(1 - k.dim * DIM);
      mesh.setColorAt(i, tint);
    }
    while (waves.length && now - waves[0].t > 1700) waves.shift();
    scrollKick *= Math.pow(0.08, dt);
    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;

    // reduced motion: render only when something changed
    if (reduced) {
      const busy = Math.abs(targetY - camY) >= 1e-4 || waves.length || pointer.on;
      if (!busy && ++stillFrames > 2) return;
      if (busy) stillFrames = 0;
    }
    renderer.render(scene, camera);
    frames++;
    if (now - windowStart > 2000) {
      const fps = (frames * 1000) / (now - windowStart);
      if (fps < 40 && level < RATIOS.length - 1) { level++; renderer.setPixelRatio(RATIOS[level]); resize(); }
      else if (fps * skip < 24 && skip < 3) skip++;
      frames = 0; windowStart = now;
    }
  }
  window.__bg3dLevel = () => level;
  window.__bg3dIcons = () => icons.map((k, i) => { mesh.getMatrixAt(i, m4); pos.setFromMatrixPosition(m4).project(camera); return [(pos.x * 0.5 + 0.5) * innerWidth, (-pos.y * 0.5 + 0.5) * innerHeight, k.glow, k.dim]; });
  requestAnimationFrame(frame);
})();
