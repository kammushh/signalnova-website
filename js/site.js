/* SignalNova website: theme toggle, spectrum instrument, whitepaper request. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);

  /* ---------- Theme menu: SignalNova (default) · Light · Dark ---------- */
  const root = document.documentElement;
  const BAR = { signalnova: "#F5F5FB", light: "#FFFFFF", dark: "#000000" };
  const themeBtn = $("themeBtn"), menu = $("themeMenu");
  const items = Array.from(menu.querySelectorAll("[data-theme-choice]"));

  function applyTheme(t) {
    root.dataset.theme = t;
    $("themeColor").setAttribute("content", BAR[t]);
    items.forEach((i) => i.setAttribute("aria-checked", String(i.dataset.themeChoice === t)));
  }
  function openMenu(open) {
    menu.classList.toggle("open", open);
    themeBtn.setAttribute("aria-expanded", String(open));
    if (open) (items.find((i) => i.getAttribute("aria-checked") === "true") || items[0]).focus();
  }
  applyTheme(root.dataset.theme || "signalnova");
  themeBtn.addEventListener("click", () => openMenu(!menu.classList.contains("open")));
  items.forEach((i) => i.addEventListener("click", () => {
    applyTheme(i.dataset.themeChoice);
    try { localStorage.setItem("sn-theme", i.dataset.themeChoice); } catch (e) { /* not saved, still applied */ }
    openMenu(false); themeBtn.focus();
  }));
  menu.addEventListener("keydown", (e) => {
    const k = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[(k + 1) % items.length].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); items[(k - 1 + items.length) % items.length].focus(); }
    if (e.key === "Escape" || e.key === "Tab") { openMenu(false); if (e.key === "Escape") themeBtn.focus(); }
  });
  document.addEventListener("click", (e) => {
    if (menu.classList.contains("open") && !e.target.closest(".theme")) openMenu(false);
  });

  $("year").textContent = new Date().getFullYear();

  /* ---------- Spectrum instrument: the 1 GHz window is the slider ---------- */
  const MIN = 0.7, MAX = 8, SPAN = MAX - MIN;   // full tuning range shown on the bar
  const LO = 1.2, HI = 7.5;                     // window centre limits (window stays on the bar)
  const pct = (f) => ((f - MIN) / SPAN) * 100;
  // Keep the ranges in sync with the "range" lines in index.html (#markets).
  const markets = {
    terrestrial: { label: "terrestrial base stations", center: 3.5, range: [0.7, 4.2] },
    orbital:     { label: "satellites and ground gateways", center: 4.0, range: [2, 8] },
    defense:     { label: "drones and portable communication", center: 2.4, range: [0.7, 8] }
  };
  const axis = $("axis"), win = $("win"), mkt = $("mkt"), ticks = $("ticks"), tip = $("tip");
  let center = 3.5;

  [0.7, 2, 3, 4, 5, 6, 7, 8].forEach((g) => {
    const s = document.createElement("span");
    s.style.left = pct(g) + "%";
    s.textContent = g + " GHz";
    ticks.appendChild(s);
  });
  win.style.width = (1 / SPAN) * 100 + "%";

  function setCenter(c) {
    center = Math.min(HI, Math.max(LO, Math.round(c * 10) / 10));
    win.style.left = pct(center - 0.5) + "%";
    $("ro-main").textContent = center.toFixed(1) + " GHz";
    $("ro-sub").textContent = "Covers " + (center - 0.5).toFixed(1) + " to " + (center + 0.5).toFixed(1) + " GHz";
    win.setAttribute("aria-valuenow", center.toFixed(1));
    win.setAttribute("aria-valuetext", center.toFixed(1) + " gigahertz");
  }
  function setMarket(key, moveWindow) {
    const m = markets[key];
    mkt.style.left = pct(m.range[0]) + "%";
    mkt.style.width = pct(m.range[1]) - pct(m.range[0]) + "%";
    $("mk-legend").textContent = "Most relevant to " + m.label;
    if (moveWindow) setCenter(m.center);
  }

  // The hint disappears for good once the visitor has moved the window.
  let used = false;
  function markUsed() {
    if (used) return;
    used = true;
    tip.classList.add("gone");
    win.classList.remove("nudge");
  }

  // Drag the window, or press anywhere on the bar to jump there.
  const freqAt = (x) => { const r = axis.getBoundingClientRect(); return MIN + ((x - r.left) / r.width) * SPAN; };
  let drag = null;
  axis.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const onWin = win.contains(e.target);
    drag = { id: e.pointerId, offset: onWin ? center - freqAt(e.clientX) : 0, moved: false };
    if (!onWin) setCenter(freqAt(e.clientX));        // animated jump
    axis.setPointerCapture(e.pointerId);
    win.focus({ preventScroll: true });
    markUsed();
  });
  axis.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (!drag.moved) { drag.moved = true; win.classList.add("dragging"); }   // follow the finger, no easing
    setCenter(freqAt(e.clientX) + drag.offset);
  });
  const endDrag = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    drag = null;
    win.classList.remove("dragging");
  };
  axis.addEventListener("pointerup", endDrag);
  axis.addEventListener("pointercancel", endDrag);

  win.addEventListener("keydown", (e) => {
    const step = { ArrowLeft: -0.1, ArrowDown: -0.1, ArrowRight: 0.1, ArrowUp: 0.1, PageDown: -0.5, PageUp: 0.5 }[e.key];
    if (step !== undefined) setCenter(center + step);
    else if (e.key === "Home") setCenter(LO);
    else if (e.key === "End") setCenter(HI);
    else return;
    e.preventDefault();
    markUsed();
  });

  // A short nudge the first time the section scrolls into view, so it reads as movable.
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      if (entries.some((en) => en.isIntersecting)) {
        io.disconnect();
        if (!used) win.classList.add("nudge");
      }
    }, { threshold: 0.6 });
    io.observe(axis);
  }
  win.addEventListener("animationend", () => win.classList.remove("nudge"));

  document.querySelectorAll('input[name="market"]').forEach((r) =>
    r.addEventListener("change", () => setMarket(r.value, true)));
  setMarket("terrestrial", true);

  // "See it on the tuning range" buttons in the Markets section
  document.querySelectorAll("[data-market]").forEach((b) => b.addEventListener("click", () => {
    const r = document.querySelector('input[name="market"][value="' + b.dataset.market + '"]');
    r.checked = true;
    setMarket(r.value, true);
    $("range").scrollIntoView({ behavior: "smooth" });
    r.focus({ preventScroll: true });
  }));

  /* ---------- Whitepaper request with e-mail verification ---------- */
  const form = $("form"), msg = $("msg");
  let stage = 1, cooldown = null;

  const say = (t, cls) => { msg.textContent = t; msg.className = "msg " + (cls || ""); };
  const show = (n) => {
    $("step1").hidden = n !== 1; $("step2").hidden = n !== 2; $("done").hidden = n !== 3;
    $("soon").hidden = n !== 4;
    stage = n; say("");
  };
  const okEmail = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e);
  const invalid = (el, bad) => el.setAttribute("aria-invalid", bad ? "true" : "false");

  async function post(url, body) {
    let r;
    try {
      r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch (e) {
      return { ok: false, message: "No connection. Check your internet and try again." };
    }
    let data = {};
    try { data = await r.json(); } catch (e) { /* not JSON */ }
    if (!r.ok && !data.message) data.message = "Something went wrong. Please try again in a moment.";
    return Object.assign({ ok: r.ok }, data);
  }

  async function sendCode() {
    const nameEl = $("name"), emailEl = $("email");
    const name = nameEl.value.trim(), email = emailEl.value.trim();
    invalid(nameEl, false); invalid(emailEl, false);
    if (!name) { say("Enter your name.", "err"); invalid(nameEl, true); nameEl.focus(); return; }
    if (!okEmail(email)) { say("Enter a valid e-mail address.", "err"); invalid(emailEl, true); emailEl.focus(); return; }
    if (!$("consent").checked) { say("Tick the box to continue.", "err"); $("consent").focus(); return; }

    // Demo build (static hosting, no backend): no code is sent, nothing is stored.
    show(4); $("soonTitle").focus(); return;

    const btn = stage === 1 ? $("send") : $("resend");
    btn.disabled = true; say("Sending code…");
    const res = await post("/api/send-code", { name, email, consent: true, website: $("website").value });
    btn.disabled = false;
    if (!res.ok) {
      say(res.message, "err");
      if (res.retry_after) startCooldown(res.retry_after);
      return;
    }
    $("sentTo").textContent = email;
    if (stage !== 2) { show(2); $("code").value = ""; $("code").focus(); }
    say("Code sent. It can take a minute to arrive. Check your spam folder too.", "ok");
    startCooldown(res.cooldown || 30);
  }

  function startCooldown(seconds) {
    const b = $("resend");
    let s = seconds;
    b.disabled = true; clearInterval(cooldown);
    b.textContent = "Send a new code (" + s + "s)";
    cooldown = setInterval(() => {
      s--;
      b.textContent = s > 0 ? "Send a new code (" + s + "s)" : "Send a new code";
      if (s <= 0) { clearInterval(cooldown); b.disabled = false; }
    }, 1000);
  }

  async function verify() {
    const email = $("email").value.trim(), codeEl = $("code");
    const code = codeEl.value.replace(/\D/g, "");
    if (code.length !== 6) { say("Enter the 6-digit code.", "err"); codeEl.focus(); return; }
    $("verify").disabled = true; say("Checking code…");
    const res = await post("/api/verify-code", { email, code });
    $("verify").disabled = false;
    if (!res.ok) {
      say(res.message, "err");
      codeEl.select();
      return;
    }
    $("doneTo").textContent = email;
    $("linkHours").textContent = res.link_hours || 72;
    $("dl").href = res.download_url;
    clearInterval(cooldown);
    show(3);
    $("doneTitle").focus();
  }

  // Digits only in the code box; submit automatically once 6 digits are in.
  $("code").addEventListener("input", (e) => {
    const v = e.target.value.replace(/\D/g, "").slice(0, 6);
    if (v !== e.target.value) e.target.value = v;
    if (v.length === 6 && !$("verify").disabled) verify();
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (stage === 1) sendCode(); else if (stage === 2) verify();
  });
  $("resend").addEventListener("click", sendCode);
  $("change").addEventListener("click", () => {
    clearInterval(cooldown);
    $("resend").disabled = false; $("resend").textContent = "Send a new code";
    show(1); $("email").focus();
  });
})();
