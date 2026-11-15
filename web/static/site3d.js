/*
 * Page-wide 3D: a parallax field of floating app-icon tiles behind the page, the scroll-driven
 * exploded build in the privacy section, the testimonial coverflow, flip cards, magnetic buttons
 * and a cursor spotlight. Pure CSS 3D transforms driven from one animation loop, so it costs
 * far less than another WebGL scene. Everything degrades to a still, readable page.
 */
(function () {
  "use strict";
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const small = () => innerWidth < 700;
  let px = 0, py = 0, sy = scrollY;
  addEventListener("pointermove", e => { px = e.clientX / innerWidth - 0.5; py = e.clientY / innerHeight - 0.5; }, { passive: true });
  addEventListener("scroll", () => { sy = scrollY; }, { passive: true });

  // ---------- floating icon field ----------
  const field = window.__bg3d ? null : document.getElementById("bg3d"); // CSS fallback when WebGL is off
  const tiles = [];
  if (field) {
    const COLORS = [["#5fd4ff", "#3b82f6"], ["#9b6bff", "#5b3bd1"], ["#4fe3a1", "#16a37a"], ["#ffb547", "#ff7a45"], ["#ff6b8b", "#c2185b"], ["#7fe0ff", "#2bb3e0"]];
    const GLYPHS = ["✓", "", "", "◎", "", "⌘", "", "✓", ""];
    const n = small() ? 9 : 18;
    for (let i = 0; i < n; i++) {
      const el = document.createElement("i");
      const z = 0.25 + Math.random() * 0.75, size = 34 + z * 58, c = COLORS[i % COLORS.length];
      el.style.cssText = "width:" + size + "px;height:" + size + "px;border-radius:" + size * 0.26 + "px;opacity:" + (0.08 + z * 0.16).toFixed(2) +
        ";background:linear-gradient(135deg," + c[0] + "," + c[1] + ")";
      el.textContent = GLYPHS[i % GLYPHS.length];
      el.style.fontSize = size * 0.42 + "px";
      field.appendChild(el);
      tiles.push({ el, z, x: Math.random() * 100, y: Math.random() * 100 * 2.2, rx: Math.random() * 6, ry: Math.random() * 6, sp: 0.4 + Math.random() * 0.6 });
    }
  }

  // ---------- privacy: exploded build ----------
  const priv = document.getElementById("private");
  const layers = priv ? [...priv.querySelectorAll(".layer")] : [];
  const stack = priv && priv.querySelector(".stack");
  const sent = priv && priv.querySelector(".sent-box");
  const meter = priv && priv.querySelector(".meter b");
  function privProgress() {
    if (!priv) return 0;
    const r = (priv.querySelector(".stack-wrap") || priv).getBoundingClientRect();
    const p = (innerHeight - r.top) / (innerHeight * 0.8); // 0 as it enters, 1 when its top is 20% from the top
    return Math.max(0, Math.min(1, p));
  }
  const ease = t => t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t);
  function fmt(bytes) { return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + " MB" : (bytes / 1024).toFixed(1) + " KB"; }
  const FULL = 45.8 * 1048576, SLIM = 2.4 * 1024;

  // ---------- testimonials coverflow ----------
  const cfg = (() => { try { return JSON.parse(document.getElementById("cfg").textContent); } catch (e) { return {}; } })();
  const love = document.getElementById("love");
  const quotes = Array.isArray(cfg.testimonials) ? cfg.testimonials.filter(t => t && t.name && t.quote) : [];
  let active = 0, cards = [], autoTimer = null;
  const esc = s => String(s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  if (love && quotes.length) {
    love.hidden = false;
    const ring = love.querySelector(".flow");
    const dots = love.querySelector(".dots");
    quotes.forEach((q, i) => {
      const card = document.createElement("figure");
      card.className = "qcard";
      card.innerHTML = '<blockquote>“' + esc(q.quote) + '”</blockquote><figcaption><span class="av">' + esc(q.name.trim()[0]) +
        '</span><span><b>' + esc(q.name) + '</b><small>' + esc(q.role || "") + '</small></span></figcaption>';
      card.addEventListener("click", () => go(i));
      ring.appendChild(card);
      cards.push(card);
      const d = document.createElement("button");
      d.type = "button";
      d.setAttribute("aria-label", "Show " + q.name + "'s review");
      d.addEventListener("click", () => go(i));
      dots.appendChild(d);
    });
    function layout() {
      const n = cards.length, w = small() ? 0.62 : 0.56;
      cards.forEach((c, i) => {
        let d = i - active;
        if (d > n / 2) d -= n;
        if (d < -n / 2) d += n;
        const a = Math.abs(d);
        c.style.transform = "translateX(" + (d * w * 100) + "%) translateZ(" + (-a * 180) + "px) rotateY(" + (-d * 32) + "deg)";
        c.style.opacity = a > 1.5 ? 0 : a > 0.5 ? 0.55 : 1;
        c.style.zIndex = 10 - a;
        c.classList.toggle("on", a === 0);
        c.setAttribute("aria-hidden", a === 0 ? "false" : "true");
      });
      [...dots.children].forEach((b, i) => b.classList.toggle("on", i === active));
    }
    function go(i) { active = (i + cards.length) % cards.length; layout(); restart(); }
    function restart() { clearInterval(autoTimer); if (!reduced && cards.length > 1) autoTimer = setInterval(() => go(active + 1), 6500); }
    love.querySelector(".prev").addEventListener("click", () => go(active - 1));
    love.querySelector(".next").addEventListener("click", () => go(active + 1));
    let x0 = null;
    ring.addEventListener("pointerdown", e => { x0 = e.clientX; });
    ring.addEventListener("pointerup", e => { if (x0 !== null && Math.abs(e.clientX - x0) > 40) go(active + (e.clientX < x0 ? 1 : -1)); x0 = null; });
    love.addEventListener("pointerenter", () => clearInterval(autoTimer));
    love.addEventListener("pointerleave", restart);
    addEventListener("resize", layout);
    layout();
    restart();
  }

  // ---------- flip cards: hover on desktop, tap on touch ----------
  document.querySelectorAll(".flip").forEach(card => {
    card.addEventListener("click", () => { if (!fine) card.classList.toggle("flipped"); });
    card.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); card.classList.toggle("flipped"); } });
  });

  // ---------- magnetic buttons + spotlight (desktop only) ----------
  const spot = document.getElementById("spot");
  if (fine && !reduced) {
    document.addEventListener("pointermove", e => {
      if (spot) spot.style.transform = "translate(" + (e.clientX - 300) + "px," + (e.clientY - 300) + "px)";
      document.querySelectorAll(".btn.mag").forEach(b => {
        const r = b.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const dx = e.clientX - cx, dy = e.clientY - cy, dist = Math.hypot(dx, dy);
        b.style.transform = dist < 110 ? "translate(" + (dx * 0.14).toFixed(1) + "px," + (dy * 0.2).toFixed(1) + "px)" : "";
      });
    }, { passive: true });
  } else if (spot) spot.remove();

  // ---------- one loop for everything ----------
  let t0 = performance.now();
  function frame(now) {
    requestAnimationFrame(frame);
    if (document.hidden) return;
    const t = (now - t0) / 1000, m = reduced ? 0 : 1;
    const vh = innerHeight;
    for (const k of tiles) {
      const y = ((k.y * vh) / 100 - sy * (0.12 + k.z * 0.38)) % (vh * 2.2);
      const yy = (y < -120 ? y + vh * 2.2 : y) + m * Math.sin(t * k.sp + k.x) * 14;
      const xx = (k.x * innerWidth) / 100 + m * px * 40 * k.z;
      k.el.style.transform = "translate3d(" + xx.toFixed(1) + "px," + yy.toFixed(1) + "px," + ((k.z - 1) * 260).toFixed(0) + "px) rotateX(" +
        ((k.rx + m * t * 9 * k.sp + py * 20) % 360).toFixed(1) + "deg) rotateY(" + ((k.ry + m * t * 12 * k.sp + px * 30) % 360).toFixed(1) + "deg)";
    }
    if (stack) {
      const p = reduced ? 1 : privProgress();
      const open = ease((p - 0.1) / 0.4), lift = ease((p - 0.5) / 0.3), gone = ease((p - 0.78) / 0.2);
      stack.style.transform = "rotateX(" + (56 - open * 6 + py * 6) + "deg) rotateZ(" + (-36 + px * 12) + "deg)";
      layers.forEach((l, i) => {
        const goes = l.classList.contains("go");
        const z = i * (8 + open * 34) + (goes ? lift * 55 : 0);
        const x = goes ? lift * 70 : 0;
        const sc = goes ? 1 - gone * 0.7 : 1;
        l.style.transform = "translate3d(" + x + "px," + (-x) + "px," + z + "px) scale(" + sc.toFixed(3) + ")";
        l.style.opacity = goes ? (1 - gone).toFixed(2) : (1 - lift * 0.5).toFixed(2);
      });
      if (sent) sent.style.opacity = gone.toFixed(2), sent.style.transform = "translateY(" + ((1 - gone) * 24).toFixed(0) + "px) scale(" + (0.9 + gone * 0.1).toFixed(3) + ")";
      if (meter) meter.textContent = fmt(FULL - (FULL - SLIM) * Math.max(lift * 0.85, gone));
    }
    if (reduced && t > 1) return; // reduced motion: draw the final state once, then stay still
  }
  requestAnimationFrame(frame);
})();
