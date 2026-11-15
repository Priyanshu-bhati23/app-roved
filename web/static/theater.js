/*
 * The scan theater: what the visitor watches between dropping an .ipa and reading the report.
 *   1. Unpack  - the real files inside their .ipa appear as tiles
 *   2. Trim    - the few parts the checks need glow and fly up; everything else locks and stays
 *   3. Check   - every check in the catalog ticks off, pass or fail, from the real result
 *   4. Verdict - the verdict card flips in (confetti when clean, a shake when blocked)
 * Exposes window.Theater = {start, files, trimmed, checking, finish, fail, reset}. Nothing here
 * changes the result; it only shows it. Respects reduced motion.
 */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const root = $("theater");
  if (!root) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const wait = ms => new Promise(r => setTimeout(r, reduced ? Math.min(ms, 60) : ms));
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const mb = n => n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : n >= 1024 ? (n / 1024).toFixed(1) + " KB" : n + " B";
  const SEV = { blocker: "var(--block)", warning: "var(--warn)", info: "var(--info)" };
  let signals = [];
  fetch("/v1/signals").then(r => r.json()).then(l => { signals = l; }).catch(() => {});

  const els = {
    name: root.querySelector(".th-name"), size: root.querySelector(".th-size"),
    steps: [...root.querySelectorAll(".th-step")], tiles: root.querySelector(".th-tiles"),
    more: root.querySelector(".th-more"), meter: root.querySelector(".th-meter"),
    checks: root.querySelector(".th-checks"), verdict: root.querySelector(".th-verdict"),
    note: root.querySelector(".th-note"),
  };

  function step(n) {
    els.steps.forEach((s, i) => { s.classList.toggle("done", i < n); s.classList.toggle("on", i === n); });
  }

  function icon(name) {
    const ext = (name.split(".").pop() || "").toLowerCase();
    if (/\.(png|jpe?g|car|heic|pdf)$/i.test(name)) return "◩";
    if (/\.(nib|storyboardc)/i.test(name)) return "▦";
    if (/\.strings$|\.lproj\//.test(name)) return "Aa";
    if (/\.plist$|xcprivacy$/.test(name)) return "⚙";
    if (/framework/.test(name)) return "◫";
    if (ext === "mobileprovision") return "✎";
    if (!name.includes(".") && !name.includes("/")) return "⌘";
    return "▪";
  }

  // ---------- public API ----------
  async function start(name, size, opts) {
    root.hidden = false;
    root.classList.remove("blocked", "clear", "needs_review", "shake", "finished");
    els.name.textContent = name;
    els.size.textContent = size ? mb(size) : "";
    els.tiles.innerHTML = ""; els.more.textContent = ""; els.meter.innerHTML = "";
    els.verdict.innerHTML = ""; els.verdict.className = "th-verdict"; els.note.textContent = "";
    els.checks.innerHTML = (signals.length ? signals : Array.from({ length: 19 }, (_, i) => ({ id: "…", title: "Check " + (i + 1) })))
      .map((s, i) => '<li data-id="' + esc(s.id) + '" style="--i:' + i + '"><i></i><span>' + esc(s.title) + '</span><b></b></li>').join("");
    step(0);
    if (!opts || opts.scroll !== false) root.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
  }

  // nested files keep their folder so two Info.plist files can be told apart
  function short(n) {
    const parts = n.split("/");
    return parts.length < 2 ? n : parts[parts.length - 2].replace(/\.(storyboardc|lproj|framework|bundle)$/, "") + "/" + parts[parts.length - 1];
  }

  // the real files inside the .ipa, before anything is trimmed
  let tileEls = [];
  async function files(list) {
    const isKeep = n => n === "Info.plist" || /PrivacyInfo\.xcprivacy$/.test(n) || n === "embedded.mobileprovision" ||
      /^Frameworks\/([^/]+)\.framework\/\1$/.test(n) || (!n.includes("/") && !n.includes("."));
    const keep = list.filter(f => isKeep(f.name));
    const rest = list.filter(f => !isKeep(f.name)).sort((a, b) => b.size - a.size);
    const MAX = innerWidth < 700 ? 22 : 40;
    const shown = keep.concat(rest.slice(0, Math.max(0, MAX - keep.length)));
    shown.sort(() => Math.random() - 0.5);
    els.tiles.innerHTML = shown.map(f => '<div class="tile' + (isKeep(f.name) ? " keep" : "") + '" title="' + esc(f.name) + '"><em>' + icon(f.name) +
      '</em><span>' + esc(short(f.name)) + '</span><small>' + mb(f.size) + '</small></div>').join("");
    tileEls = [...els.tiles.children];
    const hidden = list.length - shown.length;
    els.more.textContent = list.length.toLocaleString() + " files in this build" + (hidden > 0 ? " · showing " + shown.length : "");
    tileEls.forEach((t, i) => setTimeout(() => t.classList.add("in"), reduced ? 0 : i * 22));
    await wait(tileEls.length * 22 + 300);
  }

  async function trimmed(slimBytes, originalBytes) {
    step(1);
    tileEls.forEach((t, i) => setTimeout(() => t.classList.add(t.classList.contains("keep") ? "go" : "stay"), reduced ? 0 : 60 + (i % 12) * 30));
    const from = originalBytes, to = slimBytes, t0 = performance.now(), D = reduced ? 1 : 1100;
    await new Promise(res => {
      function tick(now) {
        const k = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - k, 3);
        els.meter.innerHTML = '<span>uploading</span><b>' + mb(Math.round(from - (from - to) * e)) + '</b><span>of ' + mb(from) + '</span>';
        if (k < 1) requestAnimationFrame(tick); else res();
      }
      requestAnimationFrame(tick);
    });
    els.note.textContent = "Everything locked stays on your device. Only the glowing parts are checked, then discarded.";
    await wait(250);
  }

  function checking() {
    step(2);
    root.classList.add("checking");
  }

  async function finish(d) {
    root.classList.remove("checking");
    step(2);
    const hits = {};
    d.findings.forEach(f => { (hits[f.signal.id] = hits[f.signal.id] || []).push(f.signal.severity); });
    const rows = [...els.checks.children];
    for (const li of rows) {
      const sev = hits[li.dataset.id];
      li.classList.add(sev ? "fail" : "pass");
      if (!sev) li.querySelector("b").textContent = "ok";
      if (sev) { li.style.setProperty("--sev", SEV[sev[0]]); li.querySelector("b").textContent = sev.length > 1 ? sev.length + "×" : sev[0]; }
      await wait(sev ? 140 : 55);
    }
    step(3);
    const words = { blocked: "Blocked", needs_review: "Needs review", clear: "Clear" };
    const c = d.counts;
    els.verdict.className = "th-verdict v-" + d.verdict;
    els.verdict.innerHTML = '<div class="vcard"><small>Verdict</small><strong>' + words[d.verdict] + '</strong><div class="vcounts">' +
      '<span><b data-n="' + c.blocker + '">0</b> blocker' + (c.blocker === 1 ? "" : "s") + '</span><span><b data-n="' + c.warning + '">0</b> warning' + (c.warning === 1 ? "" : "s") + '</span><span><b data-n="' + c.info + '">0</b> info</span></div>' +
      '<p>' + (d.verdict === "clear" ? "No build problems found. " : "") + 'Details below ↓</p></div>';
    root.classList.add(d.verdict, "finished");
    els.verdict.querySelectorAll("b[data-n]").forEach(b => {
      const n = +b.dataset.n; let i = 0;
      const id = setInterval(() => { b.textContent = ++i >= n ? n : i; if (i >= n) clearInterval(id); }, reduced ? 0 : 90);
      if (!n) { b.textContent = 0; clearInterval(id); }
    });
    if (d.verdict === "clear") confetti();
    else if (!reduced) { root.classList.add("shake"); setTimeout(() => root.classList.remove("shake"), 700); }
    await wait(700);
  }

  function fail(msg) {
    root.classList.remove("checking");
    els.note.innerHTML = '<span class="err">' + esc(msg) + "</span>";
  }

  function reset() { root.hidden = true; }

  // a scan with no files to show (the server-generated sample)
  function sampleNote() {
    els.tiles.innerHTML = '<div class="th-empty">This sample build is generated on our server, so there are no files of yours to trim. Drop your own .ipa to watch your files get sorted.</div>';
    els.more.textContent = "";
  }

  // ---------- confetti for a clean build ----------
  function confetti() {
    if (reduced) return;
    const c = document.createElement("canvas");
    c.className = "confetti";
    root.appendChild(c);
    const r = root.getBoundingClientRect();
    c.width = r.width; c.height = r.height;
    const g = c.getContext("2d"), COLORS = ["#5fd4ff", "#4fe3a1", "#ffb547", "#9b6bff", "#ff6b8b"];
    const bits = Array.from({ length: 140 }, () => ({ x: r.width / 2, y: r.height * 0.55, vx: (Math.random() - 0.5) * 14, vy: -6 - Math.random() * 10, s: 4 + Math.random() * 6, a: Math.random() * 6, va: (Math.random() - 0.5) * 0.4, c: COLORS[(Math.random() * COLORS.length) | 0] }));
    let f = 0;
    (function draw() {
      g.clearRect(0, 0, c.width, c.height);
      bits.forEach(b => { b.vy += 0.35; b.x += b.vx; b.y += b.vy; b.a += b.va; g.save(); g.translate(b.x, b.y); g.rotate(b.a); g.fillStyle = b.c; g.fillRect(-b.s / 2, -b.s / 4, b.s, b.s / 2); g.restore(); });
      if (++f < 110) requestAnimationFrame(draw); else c.remove();
    })();
  }

  window.Theater = { start, files, trimmed, checking, finish, fail, reset, sampleNote };
})();
