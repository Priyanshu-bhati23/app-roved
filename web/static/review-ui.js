/*
 * The automated review wizard: a few yes/no cards (follow-ups appear only when relevant),
 * the App Store description, then an instant report rendered on the page.
 * The rejection rescue asks only for Apple's message. Talks to POST /v1/review.
 */
(function () {
  "use strict";
  const A = window.AR;
  if (!A) return;
  const { $, esc, post, CFG, SEV } = A;
  const dlg = $("dlg"), body = $("wz-body"), next = $("wz-next"), back = $("wz-back"), err = $("dlg-err");

  // free during the beta: show the planned price crossed out
  if (CFG.beta_free) document.querySelectorAll(".pr").forEach(el => {
    el.innerHTML = 'Free<span class="was">beta · then ' + esc(el.dataset.price) + "</span>";
  });

  // [key, question, hint, follow-ups shown when the answer is yes, default]
  const QUESTIONS = [
    ["has_login", "Does someone need to log in to use the app?", "", [
      ["demo_account", "Have you added a demo account for the reviewer in App Store Connect?", "App Review Information → Sign-in required (or a full demo mode)", [
        ["demo_full_access", "Can it reach every feature with no 2FA code, SMS or expiring trial?", "", [], true]]],
      ["login_wall", "Do people have to log in before they can try anything?", "No guest mode or skip button", [
        ["account_needed", "Do the main features really depend on an account?", "Yes: synced data, messaging, a service they already pay for. No: browsing, reading, tools, single-player games"]]],
    ]],
    ["creates_accounts", "Can people create an account inside the app?", "Including guest accounts made automatically", [
      ["in_app_deletion", "Can they delete that account from inside the app?", "A link to email support doesn't count", [
        ["full_deletion", "Does it delete the account and its data, not just deactivate it, without contacting support?", "A web page linked straight from the app is fine", [], true]]],
      ["extra_personal_info", "Does sign-up require details the app doesn't need, like phone, birthday or address?", "Required fields only; optional ones are fine", [], false],
    ]],
    ["social_login", "Do you offer Google, Facebook or another social login?", "", [
      ["privacy_login", "Do you also offer Sign in with Apple (or a similar private login)?", "", [
        ["siwa_revoke", "When an account is deleted, do you revoke its Sign in with Apple tokens?", "Via the Sign in with Apple REST API", [], true]]],
      ["social_revoke", "Can people disconnect the social account from inside the app?", "Revokes the token and stops data sharing", [], true],
    ]],
    ["sells_digital", "Do you sell digital content, premium features or subscriptions?", "Not physical goods or real-world services", [
      ["uses_iap", "Are they sold through Apple's in-app purchase?", ""],
      ["subscriptions", "Are any of them auto-renewing subscriptions?", "", [
        ["terms_and_privacy_links", "Does your App Store page link to Terms of Use (EULA) and your privacy policy?", ""],
        ["deletion_billing_notice", "If people can delete their account, does that flow warn subscribers that billing continues until they cancel?", "Answer yes if accounts can't be deleted or created", [], true]]],
    ]],
    ["privacy_policy", "Is a privacy policy linked in App Store Connect and inside the app?", "", [], true],
    ["user_content", "Can people post content or message each other?", "Posts, comments, chat, profiles", [["report_and_block", "Can users report content and block other users?", ""]]],
    ["kids_category", "Is the app in the Kids category?", "", [["third_party_ads_analytics", "Does it include third-party ads or analytics SDKs?", ""]]],
    ["tracks_users", "Do you track users across other companies' apps or websites?", "For ads or attribution, e.g. ad SDKs with an IDFA", [["uses_att", "Do you ask permission with App Tracking Transparency first?", ""]]],
    ["mostly_web", "Is the app mostly a website shown in a web view?", ""],
    ["review_notes", "Have you written review notes explaining how to reach every feature?", "", [], true],
  ];

  let plan = "review", page = 0, answers = {};
  const PAGES = { review: ["q1", "q2", "desc"], rescue: ["rej"] };

  function ynHTML(key, def) {
    const v = key in answers ? answers[key] : def;
    if (!(key in answers) && def !== undefined) answers[key] = def;
    return '<div class="yn" data-key="' + key + '"><button type="button" class="y' + (v === true ? " on" : "") + '">Yes</button><button type="button" class="n' + (v === false ? " on" : "") + '">No</button></div>';
  }
  function qHTML(q, i) {
    const [key, text, hint, subs = [], def] = q;
    const open = answers[key] === true;
    return '<div class="q" style="--i:' + i + '"><p>' + esc(text) + (hint ? "<small>" + esc(hint) + "</small>" : "") + "</p>" + ynHTML(key, def) +
      subs.map(sq => '<div class="sub-q" data-parent="' + key + '"' + (open ? "" : " hidden") + "><p>" + esc(sq[1]) + (sq[2] ? "<small>" + esc(sq[2]) + "</small>" : "") + "</p>" + ynHTML(sq[0], sq[4]) +
        (sq[3] || []).map(ssq => '<div class="sub-q" data-parent="' + sq[0] + '"' + (answers[sq[0]] === true ? "" : " hidden") + "><p>" + esc(ssq[1]) + (ssq[2] ? "<small>" + esc(ssq[2]) + "</small>" : "") + "</p>" + ynHTML(ssq[0], ssq[4]) + "</div>").join("") + "</div>").join("") + "</div>";
  }

  function render() {
    err.hidden = true;
    const steps = PAGES[plan], key = steps[page];
    $("wz-step").textContent = plan === "review" ? "Full AI review · step " + (page + 1) + " of " + steps.length : "Rejection rescue";
    $("wz-bar").style.width = ((page + 1) / (steps.length + 1)) * 100 + "%";
    back.style.visibility = page ? "visible" : "hidden";
    next.textContent = page === steps.length - 1 ? (plan === "review" ? "Get my review" : "Decode it") : "Next";
    const scan = A.getScan();
    if (key === "q1" || key === "q2") {
      $("wz-title").textContent = key === "q1" ? "Accounts, login and payments" : "Content, privacy and tracking";
      const qs = key === "q1" ? QUESTIONS.slice(0, 4) : QUESTIONS.slice(4);
      body.innerHTML = (key === "q1" ? detected(scan) : "") + qs.map(qHTML).join("");
    } else if (key === "desc") {
      $("wz-title").textContent = "Your App Store description";
      body.innerHTML = '<div class="q"><p>Paste your App Store description (optional)<small>We look for wording reviewers flag: other platforms, beta or coming-soon language, placeholder text.</small></p><textarea class="in" id="wz-desc" maxlength="8000" placeholder="Paste the description from App Store Connect">' + esc(answers.description || "") + "</textarea></div>" +
        '<div class="q"><p>' + (scan ? "✓ Your scan of <b>" + esc(scan.app_name) + "</b> will be included" : "No build scanned yet") + "<small>" + (scan ? "Build findings and setup findings end up in one fix list." : "You can still get the setup review. Scan an .ipa first to include build checks.") + "</small></p></div>" +
        '<div class="q"><p>Email (optional)<small>Only so we can tell you about updates. Your report appears right here, nothing is emailed.</small></p><input class="in" id="wz-email" type="email" maxlength="200" autocomplete="email" value="' + esc(answers.email || "") + '"></div>';
    } else {
      $("wz-title").textContent = "Paste Apple's rejection";
      body.innerHTML = '<div class="q"><p>Message from App Review<small>Copy it from App Store Connect → your version → App Review. Include the "Guideline x.x" line.</small></p><textarea class="in" id="wz-rej" maxlength="6000" style="min-height:160px" placeholder="Guideline 5.1.1 - Legal - Privacy - Data Collection and Storage ...">' + esc(answers.rejection || "") + "</textarea></div>" +
        (scan ? '<div class="q"><p>✓ Your scan of <b>' + esc(scan.app_name) + "</b> will be included<small>So build problems show up in the same report.</small></p></div>" : "") +
        '<div class="q"><p>Email (optional)<small>Only for updates. The answer appears right here.</small></p><input class="in" id="wz-email" type="email" maxlength="200" autocomplete="email" value="' + esc(answers.email || "") + '"></div>';
    }
  }

  // what the build already told us about sign-in: pre-answer it and say so
  let prefilled = null;
  function detected(scan) {
    const a = scan && scan.auth;
    if (!a || !a.social_login_sdks) return "";
    const sdks = Object.keys(a.social_login_sdks), siwa = a.sign_in_with_apple || {};
    const hasSiwa = !!(siwa.used || siwa.entitlement);
    if (prefilled !== scan) {
      prefilled = scan;
      if (sdks.length) { answers.has_login = true; answers.social_login = true; }
      if (sdks.length || hasSiwa) answers.privacy_login = hasSiwa;
    }
    if (!sdks.length && !hasSiwa) return "";
    const bits = [];
    if (sdks.length) bits.push(sdks.map(esc).join(", "));
    bits.push(hasSiwa ? "Sign in with Apple" : "no Sign in with Apple");
    return '<div class="q detected"><p>🔎 Found in your build: <b>' + bits.join(" · ") + "</b><small>We pre-filled those answers. Change them if they're wrong.</small></p></div>";
  }

  body.addEventListener("click", e => {
    const b = e.target.closest(".yn button");
    if (!b) return;
    const yn = b.parentElement, key = yn.dataset.key, val = b.classList.contains("y");
    answers[key] = val;
    yn.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
    body.querySelectorAll('.sub-q[data-parent="' + key + '"]').forEach(s => { s.hidden = !val; });
  });

  function keep() {
    const d = $("wz-desc"), m = $("wz-email"), r = $("wz-rej");
    if (d) answers.description = d.value;
    if (m) answers.email = m.value.trim();
    if (r) answers.rejection = r.value;
  }

  function open(p) {
    plan = p; page = 0;
    render();
    dlg.showModal();
  }
  document.addEventListener("click", e => {
    const b = e.target.closest(".order");
    if (b) { e.preventDefault(); open(b.dataset.plan); }
    if (e.target.id === "cancel") dlg.close();
  });
  back.onclick = () => { keep(); if (page) { page--; render(); } };
  next.onclick = async () => {
    keep();
    if (plan === "rescue" && !(answers.rejection || "").trim()) { err.textContent = "Paste the message from App Review first."; err.hidden = false; return; }
    if (page < PAGES[plan].length - 1) { page++; render(); body.scrollTop = 0; return; }
    await generate();
  };

  async function generate() {
    $("wz-bar").style.width = "100%";
    body.innerHTML = '<div class="gen"><div class="orb"></div><b>' + (plan === "review" ? "Checking your build and setup against Apple's guidelines…" : "Reading Apple's message…") + "</b><span>Usually a few seconds. Explanations come from the published guidelines.</span></div>";
    next.disabled = back.disabled = true;
    const profile = {};
    QUESTIONS.forEach(function walk(q) { if (q[0] in answers) profile[q[0]] = answers[q[0]]; (q[3] || []).forEach(walk); });
    profile.description = answers.description || "";
    const payload = { plan, email: answers.email || "", scan: A.getScan() || null };
    if (plan === "review") payload.profile = profile; else payload.rejection = answers.rejection;
    try {
      const rv = await post("/v1/review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      dlg.close();
      show(rv);
    } catch (e2) {
      render();
      err.textContent = e2.message || "Something went wrong. Please try again.";
      err.hidden = false;
    } finally {
      next.disabled = back.disabled = false;
    }
  }

  const SOURCE = { build: "Build", setup: "App Store Connect", description: "Description" };
  function show(rv) {
    const out = $("rv-out"), c = rv.counts;
    let html = '<div class="rv-head ' + esc(rv.verdict) + '"><small>' + (plan === "review" ? "Full AI review" : "Rejection rescue") + "</small><h3>" + esc(rv.headline) + "</h3>" +
      '<div class="vcounts"><span><b>' + c.blocker + "</b> blocker" + (c.blocker === 1 ? "" : "s") + "</span><span><b>" + c.warning + "</b> warning" + (c.warning === 1 ? "" : "s") + "</span><span><b>" + c.info + "</b> info</span></div></div>";
    if (rv.rejection) {
      const r = rv.rejection;
      html += '<div class="rv-rescue"><div class="rv-tags">' + (r.guidelines.length ? r.guidelines.map(g => '<span class="tag sev" style="--sev:var(--acc)">Guideline ' + esc(g) + "</span>").join("") : '<span class="tag">No guideline number found</span>') + "</div>" +
        "<h4 style=\"margin-top:10px\">What Apple is saying</h4><p>" + esc(r.meaning).replace(/[\[【](kb:[a-z0-9-]+#\d+)[\]】]/g, "") + "</p>" +
        "<h4>What to change</h4><ol>" + r.steps.map(s => "<li>" + esc(s) + "</li>").join("") + "</ol>" +
        '<h4>Your reply to App Review</h4><div class="rv-reply" id="rv-reply">' + esc(r.reply) + "</div>" +
        '<div class="rv-actions"><button class="btn sm" type="button" id="rv-copy">Copy reply</button></div></div>';
    }
    if (rv.items.length) {
      html += '<ol class="rv-list">' + rv.items.map((it, i) => '<li class="rv-item" style="--sev:' + SEV[it.severity] + ";--i:" + i + '"><div class="rv-tags"><span class="tag sev">' + esc(it.severity) + '</span><span class="tag">' + esc(SOURCE[it.source] || it.source) + '</span><span class="tag">' + esc(it.id) + "</span></div>" +
        "<h4>" + esc(it.title) + "</h4><p>" + esc(it.why).replace(/[\[【](kb:[a-z0-9-]+#\d+)[\]】]/g, "") + "</p><p><b>Fix:</b> " + esc(it.fix) + "</p>" +
        (it.link ? '<a href="' + esc(it.link) + '" target="_blank" rel="noopener">Apple guideline ↗</a>' : "") + "</li>").join("") + "</ol>";
    } else if (!rv.rejection) {
      html += '<p style="margin-top:14px;color:var(--muted)">Nothing in your build or your answers matches a known rejection reason. Double-check your screenshots show the app in use, then submit.</p>';
    }
    html += '<div class="rv-actions"><button class="btn ghost sm" type="button" onclick="window.print()">Save as PDF</button><button class="btn ghost sm order" type="button" data-plan="' + (plan === "review" ? "rescue" : "review") + '">' + (plan === "review" ? "Already rejected? Decode it" : "Run the full review") + "</button></div>" +
      '<p class="rv-disc">' + esc(rv.disclaimer) + "</p>";
    out.innerHTML = html;
    const copy = $("rv-copy");
    if (copy) copy.onclick = () => {
      const t = $("rv-reply").textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(() => { copy.textContent = "Copied ✓"; }, () => { copy.textContent = "Select and copy the text above"; });
    };
    out.scrollIntoView({ behavior: "smooth", block: "start" });
    try { window.Mascot && window.Mascot.say(rv.verdict === "ready" ? "Looking good. Check your screenshots show the app in use, then submit." : "Start at number 1: the list is ordered by what's most likely to get you rejected.", { label: "Rovy", ms: 9000 }); } catch (e) { /* optional */ }
  }
})();
