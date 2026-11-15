/*
 * Rovy, the App-roved mascot: a small 3D reviewer robot in the corner of the page that drops a
 * new App Store tip each time (click it, wait, scroll to a new section, or finish a scan).
 * Tips are shuffled and never repeat until all have been shown. Needs three.js (already on the
 * page); without WebGL the mascot stays hidden. Exposes window.Mascot = {say, react}.
 */
(function () {
  "use strict";
  const wrap = document.getElementById("rovy");
  window.Mascot = { say() {}, react() {} };
  if (!wrap || !window.THREE) return;
  const THREE = window.THREE;
  const reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canvas = wrap.querySelector("canvas");
  const bubble = wrap.querySelector(".rovy-bubble");
  const textEl = wrap.querySelector(".rovy-text");
  const countEl = wrap.querySelector(".rovy-count");

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch (e) {
    return;
  }
  wrap.hidden = false;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputEncoding = THREE.sRGBEncoding;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
  camera.position.set(0, 0.35, 7.4);
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(2, 3, 4);
  scene.add(key);
  const rim = new THREE.PointLight(0x5fd4ff, 1.6, 10);
  rim.position.set(-2.5, 1, 1.5);
  scene.add(rim);

  // ---------- materials ----------
  const shell = new THREE.MeshStandardMaterial({ color: 0xeef2fb, metalness: 0.15, roughness: 0.35 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x0b0e1c, metalness: 0.3, roughness: 0.25 });
  const glow = new THREE.MeshBasicMaterial({ color: 0x5fd4ff });
  const accent = new THREE.MeshStandardMaterial({ color: 0x5fd4ff, emissive: 0x1a6f8f, metalness: 0.2, roughness: 0.4 });

  function rounded(w, h, r) {
    const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
    s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
    s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
    s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
    return s;
  }
  function slab(w, h, r, d, bevel) {
    const g = new THREE.ExtrudeGeometry(rounded(w, h, r), { depth: d, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 6, curveSegments: 20 });
    g.center();
    return g;
  }

  // ---------- body ----------
  const bot = new THREE.Group();
  scene.add(bot);

  const head = new THREE.Group();
  head.position.y = 0.72;
  bot.add(head);
  head.add(new THREE.Mesh(slab(1.5, 1.18, 0.42, 0.7, 0.16), shell));
  const visor = new THREE.Mesh(new THREE.ShapeGeometry(rounded(1.16, 0.78, 0.3), 20), dark);
  visor.position.z = 0.52;
  head.add(visor);
  const eyeGeo = new THREE.CircleGeometry(0.1, 24);
  const eyes = [-0.25, 0.25].map(x => {
    const e = new THREE.Mesh(eyeGeo, glow.clone());
    e.position.set(x, 0.06, 0.53);
    e.scale.y = 1.35;
    head.add(e);
    return e;
  });
  const mouth = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.025, 8, 24, Math.PI), glow.clone());
  mouth.rotation.z = Math.PI;
  mouth.position.set(0, -0.14, 0.53);
  head.add(mouth);
  [-1, 1].forEach(side => {
    const ear = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.14, 24), accent);
    ear.rotation.z = Math.PI / 2;
    ear.position.set(side * 0.86, 0, 0);
    head.add(ear);
  });
  const stalk = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.34, 12), dark);
  stalk.position.y = 0.76;
  head.add(stalk);
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.1, 20, 16), glow.clone());
  bulb.position.y = 0.96;
  head.add(bulb);

  const torso = new THREE.Mesh(new THREE.SphereGeometry(0.62, 32, 24), shell);
  torso.scale.set(1, 0.82, 0.78);
  torso.position.y = -0.38;
  bot.add(torso);
  // chest badge with a check mark
  const badgeTex = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const g = c.getContext("2d");
    g.fillStyle = "#5fd4ff"; g.beginPath(); g.arc(64, 64, 60, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "#03141c"; g.lineWidth = 16; g.lineCap = "round"; g.lineJoin = "round";
    g.beginPath(); g.moveTo(36, 66); g.lineTo(56, 86); g.lineTo(94, 44); g.stroke();
    return new THREE.CanvasTexture(c);
  })();
  const badge = new THREE.Mesh(new THREE.CircleGeometry(0.2, 32), new THREE.MeshBasicMaterial({ map: badgeTex, transparent: true }));
  badge.position.set(0, -0.3, 0.5);
  bot.add(badge);

  const arms = [-1, 1].map(side => {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.6, -0.2, 0);
    const arm = new THREE.Mesh(new THREE.SphereGeometry(0.15, 20, 16), shell);
    arm.scale.set(1, 2.1, 1);
    arm.position.y = -0.26;
    pivot.add(arm);
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 12), accent);
    hand.position.y = -0.58;
    pivot.add(hand);
    pivot.rotation.z = side * 0.35;
    bot.add(pivot);
    return pivot;
  });
  const shadow = new THREE.Mesh(new THREE.CircleGeometry(0.6, 32), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -1.18;
  scene.add(shadow);

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);
  resize();

  // ---------- tips ----------
  const TIPS = [
    "Every permission prompt needs a purpose string that says why. “We need your camera” isn't enough.",
    "If your app has a login, put a working demo account in App Store Connect for the reviewer.",
    "Apps that call APIs like UserDefaults or file timestamps need a privacy manifest that says why.",
    "Placeholder text like “Lorem ipsum” anywhere in the app is a fast way to get rejected.",
    "Screenshots should show the app actually in use, not just a splash screen or marketing art.",
    "Selling digital content or premium features? Apple usually requires in-app purchase for that.",
    "Offer Google or Facebook sign-in? You also need a privacy-focused option like Sign in with Apple.",
    "If people can create an account in your app, they must be able to delete it in the app too.",
    "An app that is just a website in a wrapper is often rejected under 4.2, Minimum Functionality.",
    "Crashes and broken flows fall under guideline 2.1, one of the most common rejection reasons.",
    "Your App Privacy answers must match what your app and every SDK in it actually collect.",
    "Mentioning Android or other platforms in your screenshots or description can get pushback.",
    "Tracking users across apps? Ask with App Tracking Transparency first, and say why in the prompt.",
    "A rejection isn't final. Fix it and resubmit, or reply to App Review in App Store Connect.",
    "Apple says most submissions are reviewed within 24 hours. A rejection costs you at least another day.",
    "Apps in the Kids category can't include third-party ads or analytics that track children.",
    "Beta or demo versions don't belong in App Review. Use TestFlight for testing.",
    "Hidden or undocumented features break guideline 2.3.1. Tell the reviewer about everything.",
    "A few lines in the review notes about non-obvious features can save a whole rejection round.",
    "UIWebView is retired. Apple no longer accepts new apps or updates that use it.",
    "Apple raises the minimum Xcode and SDK version for uploads every year. Check yours before submitting.",
    "Health, finance and legal apps often need to be published by a company, not an individual.",
    "Background location needs a clear benefit to the user. Expect the reviewer to ask why.",
    "Your app name, subtitle and keywords can't stuff in competitor names or trademarks.",
    "Signed with a development profile? It won't upload. Use an App Store distribution certificate.",
  ];
  const SECTION_TIPS = {
    checks: "Each check reads your actual build: the binary, Info.plist and privacy manifests.",
    how: "Many rejections are about screenshots, demo accounts and privacy answers, not code. That's what a review covers.",
    pricing: "Already rejected? A rescue includes a reply to App Review, written for you.",
    faq: "Your compiled code never leaves your computer. The build is trimmed in your browser first.",
  };
  let order = [], shown = 0;
  function nextTip() {
    if (!order.length) {
      order = TIPS.map((_, i) => i);
      for (let i = order.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
    }
    shown++;
    return { text: TIPS[order.pop()], label: "App Store tip #" + shown };
  }

  // ---------- behaviour ----------
  let wave = 0, jump = 0, shake = 0, nod = 0, blinkAt = 2, eyeColor = new THREE.Color(0x5fd4ff), eyeTimer = 0;
  let closed = false, hideTimer = null, idleTimer = null;
  const BASE = new THREE.Color(0x5fd4ff);
  function setEyes(hex, seconds) {
    eyeColor.set(hex);
    eyeTimer = seconds;
  }
  function say(text, opts) {
    opts = opts || {};
    textEl.textContent = text;
    countEl.textContent = opts.label || "Rovy";
    bubble.classList.remove("show");
    void bubble.offsetWidth;
    bubble.classList.add("show");
    wrap.classList.add("talking");
    wave = 1.6;
    nod = 1;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { bubble.classList.remove("show"); wrap.classList.remove("talking"); }, opts.ms || 9000);
    schedule();
  }
  function schedule() {
    clearTimeout(idleTimer);
    if (closed) return;
    idleTimer = setTimeout(() => { if (!document.hidden && !document.querySelector("dialog[open]") && !blocksSomething()) { const t = nextTip(); say(t.text, { label: t.label }); } else schedule(); }, 26000);
  }
  function tipNow() { closed = false; const t = nextTip(); say(t.text, { label: t.label }); }

  wrap.querySelector(".rovy-bot").addEventListener("click", tipNow);
  wrap.querySelector(".rovy-next").addEventListener("click", e => { e.stopPropagation(); tipNow(); });
  wrap.querySelector(".rovy-close").addEventListener("click", e => {
    e.stopPropagation();
    closed = true;
    bubble.classList.remove("show");
    wrap.classList.remove("talking");
    clearTimeout(idleTimer);
  });

  const said = new Set();
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(es => es.forEach(en => {
      const id = en.target.id;
      if (en.isIntersecting && !said.has(id) && !closed && SECTION_TIPS[id] && !blocksSomething()) { said.add(id); say(SECTION_TIPS[id], { label: "Rovy" }); }
    }), { threshold: 0.35 });
    Object.keys(SECTION_TIPS).forEach(id => { const el = document.getElementById(id); if (el) io.observe(el); });
  }
  // The first hello waits until the bubble wouldn't cover the upload box or the headline.
  const HELLO = "Hi, I'm Rovy. Tap me for an App Store tip, or tap the background to send a wave.";
  function blocksSomething() {
    if (bubble.classList.contains("show")) return false;
    const b = bubble.getBoundingClientRect();
    return [...document.querySelectorAll("#drop, h1, .hero .btn, #sample, .stage")].some(el => {
      const r = el.getBoundingClientRect();
      return r.width && r.bottom > 0 && r.top < innerHeight && !(r.right < b.left - 8 || r.left > b.right + 8 || r.bottom < b.top - 8 || r.top > b.bottom + 8);
    });
  }
  function hello() {
    if (closed || bubble.classList.contains("show")) return;
    if (blocksSomething()) { addEventListener("scroll", helloLater, { passive: true, once: true }); return; }
    say(HELLO, { label: "Rovy", ms: 7000 });
  }
  function helloLater() { setTimeout(hello, 600); }
  setTimeout(hello, 2500);

  function react(d) {
    if (!d) return;
    const b = d.counts.blocker, w = d.counts.warning;
    if (d.verdict === "clear") {
      setEyes(0x4fe3a1, 5); jump = 1;
      say("No build problems found. Next stop: screenshots, privacy answers and a demo account.", { label: "Rovy", ms: 11000 });
    } else if (b) {
      setEyes(0xff5d73, 4); shake = 1;
      say(b + (b === 1 ? " blocker" : " blockers") + " found. Fix the red ones first: each one alone can get the build rejected.", { label: "Rovy", ms: 11000 });
    } else {
      setEyes(0xffb547, 4); nod = 1;
      say(w + (w === 1 ? " warning" : " warnings") + ". Not rules, but reviewers often push back on these.", { label: "Rovy", ms: 11000 });
    }
  }
  window.Mascot = { say, react };

  // look toward the pointer anywhere on the page
  let lx = 0, ly = 0;
  window.addEventListener("pointermove", e => {
    const r = canvas.getBoundingClientRect();
    lx = Math.max(-1, Math.min(1, (e.clientX - (r.left + r.width / 2)) / 500));
    ly = Math.max(-1, Math.min(1, (e.clientY - (r.top + r.height / 2)) / 500));
  }, { passive: true });

  const clock = new THREE.Clock();
  let last = 0;
  function frame() {
    requestAnimationFrame(frame);
    if (document.hidden) return;
    const open = !!document.querySelector("dialog[open]");
    wrap.classList.toggle("away", open);
    const t = clock.getElapsedTime();
    if (t - last < 1 / 30) return; // a small corner character doesn't need more than 30 fps
    const dt = Math.min(0.06, t - last);
    last = t;
    const m = reduced ? 0 : 1;

    bot.position.y = m * Math.sin(t * 1.8) * 0.06 + Math.sin(Math.min(1, jump) * Math.PI) * 0.45 * m;
    jump = Math.max(0, jump - dt * 1.6);
    head.rotation.y += (lx * 0.6 + Math.sin(shake * 30) * shake * 0.35 * m - head.rotation.y) * 0.12;
    head.rotation.x += (ly * 0.35 + Math.sin(nod * Math.PI * 2) * nod * 0.25 * m - head.rotation.x) * 0.12;
    shake = Math.max(0, shake - dt * 1.4);
    nod = Math.max(0, nod - dt * 1.5);
    bot.rotation.y = lx * 0.25;
    bulb.scale.setScalar(1 + Math.sin(t * 4) * 0.12 * m);

    // right arm waves while talking, left arm sways
    const waving = wave > 0 && m;
    arms[1].rotation.z += ((waving ? 2.5 + Math.sin(t * 14) * 0.45 : 0.35 + Math.sin(t * 1.8) * 0.05) - arms[1].rotation.z) * 0.18;
    arms[0].rotation.z += ((-0.35 - Math.sin(t * 1.8) * 0.05 * m) - arms[0].rotation.z) * 0.18;
    wave = Math.max(0, wave - dt);

    // blink, mouth talks, eye colour fades back
    blinkAt -= dt;
    const blink = blinkAt < 0 ? Math.max(0.1, Math.abs(blinkAt + 0.08) / 0.08) : 1;
    if (blinkAt < -0.16) blinkAt = 2 + Math.random() * 3;
    eyes.forEach(e => { e.scale.y = 1.35 * Math.min(1, blink); });
    const talking = wrap.classList.contains("talking") && m;
    mouth.scale.set(1, talking ? 1 + Math.abs(Math.sin(t * 16)) * 1.6 : 1, 1);
    eyeTimer = Math.max(0, eyeTimer - dt);
    const c = eyeTimer > 0 ? eyeColor : BASE;
    eyes.forEach(e => e.material.color.lerp(c, 0.15));
    mouth.material.color.lerp(c, 0.15);
    bulb.material.color.lerp(c, 0.15);
    shadow.scale.setScalar(1 - bot.position.y * 0.6);

    renderer.render(scene, camera);
  }
  frame();
})();
