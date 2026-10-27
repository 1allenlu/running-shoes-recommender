"use strict";

/* Fitted web app: scan -> confirm -> about you -> picks, on top of the JSON API. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const WIDTHS = ["3A", "2A", "A", "B", "C", "D", "E", "2E", "3E"];
const SCALES = [
  { key: "arch_height", label: "Arch height", bands: ["low", "medium", "high"] },
  { key: "instep_height", label: "Instep height", bands: ["low", "medium", "high"] },
  { key: "heel_width", label: "Heel width", bands: ["narrow", "medium", "wide"] },
  { key: "pressure", label: "Pressure", bands: ["medial", "centered", "lateral"], optional: true },
  { key: "arch_flexibility", label: "Arch flexibility", bands: ["flexible", "moderate", "rigid"], optional: true },
];
const BAND_CENTER = [0.17, 0.5, 0.83];
const GOALS = ["Daily training", "5K / 10K", "Half marathon", "Marathon", "Speed work", "Getting back into running"];
const WORKING_LINES = [
  "Reading your scan…",
  "Matching toe box and width…",
  "Checking upper volume and heel hold…",
  "Comparing fit notes…",
  "Choosing your size in each brand…",
  "Finding pairs in stock…",
];
const PROGRESS = { welcome: 0, scan: 20, confirm: 45, about: 70, working: 88, results: 100 };
const STEP_ORDER = ["scan", "confirm", "about", "results"];
const STORE_KEY = "fitted.session";

const state = {
  userId: null,
  taskId: null,
  files: [],
  profile: null,
  questionnaire: { weekly_km: 30, goals: [], feel: "balanced", budget_usd: 160, loved: [], disliked: [] },
  result: null,
  llmReady: true,
  feedbackPick: null,
  rating: 0,
};

/* ---------- Storage (best effort; the app works without it) ---------- */

function save() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ userId: state.userId, taskId: state.taskId }));
  } catch { /* private mode or blocked storage */ }
}
function load() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
  } catch {
    return {};
  }
}
function clearSaved() {
  try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
}

/* ---------- API ---------- */

async function api(path, { method = "GET", json, form } = {}) {
  const init = { method, headers: {} };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error("Can't reach the server. Is it running?");
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(errorMessage(body) || `Something went wrong (${res.status}).`);
    err.status = res.status;
    throw err;
  }
  return body;
}

function errorMessage(body) {
  if (!body || !body.detail) return null;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail
      .map((d) => `${(d.loc || []).filter((p) => p !== "body").join(" › ")}: ${d.msg}`)
      .join("\n");
  }
  return null;
}

function friendlyAiError(message) {
  if (/API_KEY|not set|not reachable|not pulled|api key|authentication|401|403/i.test(message)) {
    return "The AI model isn't set up yet. Add a key to .env and restart the server.";
  }
  return message;
}

/* ---------- UI helpers ---------- */

let toastTimer;
function toast(message, { error = false } = {}) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.hidden = false;
  el.style.animation = "none";
  void el.offsetWidth; // restart the entrance animation
  el.style.animation = "";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), error ? 6000 : 3200);
}

function busy(button, on) {
  if (!button) return;
  button.classList.toggle("busy", on);
  button.disabled = on;
}

function cap(word) {
  return word ? word[0].toUpperCase() + word.slice(1) : "";
}

function widthLabel(width) {
  return { standard: "Standard width", wide: "Wide", "extra-wide": "Extra wide" }[width] || width;
}

function fmtSize(n) {
  return Number.isInteger(n) ? `${n}` : `${n}`.replace(/(\.\d)0+$/, "$1");
}

function setFill(range) {
  const pct = ((range.value - range.min) / (range.max - range.min)) * 100;
  range.style.setProperty("--fill", `${pct}%`);
}

function bindSegmented(group, value, onChange) {
  const buttons = $$("button", group);
  const select = (v) => buttons.forEach((b) => b.setAttribute("aria-checked", String(b.dataset.value === v)));
  select(value);
  buttons.forEach((b) => {
    b.tabIndex = 0;
    b.onclick = () => {
      select(b.dataset.value);
      onChange(b.dataset.value);
    };
  });
  group.onkeydown = (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    const i = buttons.findIndex((b) => b.getAttribute("aria-checked") === "true");
    const next = buttons[(i + (e.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
    next.click();
    next.focus();
  };
}

/* ---------- Navigation between screens ---------- */

let current = "welcome";

function show(name, { focus = true } = {}) {
  const swap = () => {
    $$(".screen").forEach((s) => (s.hidden = s.dataset.screen !== name));
    current = name;
    $(".progress span").style.width = `${PROGRESS[name] ?? 0}%`;
    $(".progress span").style.opacity = name === "welcome" ? "0" : "1";
    const stepIndex = STEP_ORDER.indexOf(name === "working" ? "about" : name);
    $$(".steps li").forEach((li, i) => {
      li.classList.toggle("current", i === stepIndex);
      li.classList.toggle("done", stepIndex > -1 && i < stepIndex);
    });
    $('[data-action="restart"]').hidden = name === "welcome";
    window.scrollTo(0, 0);
    if (focus) {
      const heading = $(`[data-screen="${name}"] h1`);
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
    }
  };
  if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.startViewTransition(swap);
  } else {
    swap();
  }
}

/* ---------- Status banner ---------- */

async function checkStatus() {
  try {
    const status = await api("/status");
    state.llmReady = status.llm_ready;
    if (!status.llm_ready) {
      const banner = $("#status-banner");
      banner.innerHTML =
        "<strong>The AI model isn't set up yet.</strong> Reading scans and finding shoes need it. " +
        "Add <code>LLM_PROVIDER</code> and a key to <code>.env</code>, then restart the server. " +
        "You can still enter your scan by hand.";
      banner.title = status.reason || "";
      banner.hidden = false;
    }
  } catch {
    /* status is a nicety; ignore failures */
  }
}

/* ---------- Users ---------- */

async function ensureUser() {
  if (state.userId) return state.userId;
  const user = await api("/users", { method: "POST" });
  state.userId = user.id;
  save();
  return user.id;
}

/* ---------- Scan upload ---------- */

const ACCEPTED = ["image/png", "image/jpeg", "image/webp", "application/pdf"];

function addFiles(list) {
  const added = [...list].filter((f) => {
    if (!ACCEPTED.includes(f.type)) {
      toast(`${f.name} isn't a PNG, JPEG or PDF.`, { error: true });
      return false;
    }
    return !state.files.some((g) => g.name === f.name && g.size === f.size);
  });
  state.files.push(...added);
  renderFiles();
}

function renderFiles() {
  const list = $("#file-list");
  list.replaceChildren(
    ...state.files.map((file, i) => {
      const li = document.createElement("li");
      li.className = "file";
      let thumb;
      if (file.type.startsWith("image/")) {
        thumb = document.createElement("img");
        thumb.src = URL.createObjectURL(file);
        thumb.alt = "";
        thumb.onload = () => URL.revokeObjectURL(thumb.src);
      } else {
        thumb = document.createElement("span");
        thumb.textContent = "PDF";
      }
      thumb.className = "file-thumb";
      const name = Object.assign(document.createElement("span"), { className: "file-name", textContent: file.name });
      const size = Object.assign(document.createElement("span"), {
        className: "file-size",
        textContent: `${Math.max(1, Math.round(file.size / 1024))} KB`,
      });
      const remove = Object.assign(document.createElement("button"), { type: "button", textContent: "✕" });
      remove.setAttribute("aria-label", `Remove ${file.name}`);
      remove.onclick = () => {
        state.files.splice(i, 1);
        renderFiles();
      };
      li.append(thumb, name, size, remove);
      return li;
    }),
  );
  $('[data-action="upload"]').disabled = state.files.length === 0;
}

function setupDropzone() {
  const zone = $("#dropzone");
  const input = $("#scan-input");
  input.onchange = () => {
    addFiles(input.files);
    input.value = "";
  };
  ["dragenter", "dragover"].forEach((t) =>
    zone.addEventListener(t, (e) => {
      e.preventDefault();
      zone.classList.add("over");
    }),
  );
  ["dragleave", "drop"].forEach((t) =>
    zone.addEventListener(t, (e) => {
      e.preventDefault();
      zone.classList.remove("over");
    }),
  );
  zone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
}

async function upload(button) {
  busy(button, true);
  try {
    const userId = await ensureUser();
    const form = new FormData();
    state.files.forEach((f) => form.append("files", f, f.name));
    const scan = await api(`/users/${userId}/scans`, { method: "POST", form });
    state.profile = scan.parsed_profile;
    renderProfile();
    show("confirm");
  } catch (e) {
    toast(friendlyAiError(e.message), { error: true });
  } finally {
    busy(button, false);
  }
}

/* ---------- Confirm profile ---------- */

function blankFoot() {
  return {
    us_size: 9,
    width: "D",
    arch_height: { band: "medium", position: 0.5 },
    instep_height: { band: "medium", position: 0.5 },
    heel_width: { band: "medium", position: 0.5 },
    pressure: null,
    arch_flexibility: null,
  };
}

function longerSide() {
  const { left, right } = state.profile;
  return Number(left.us_size) >= Number(right.us_size) ? "left" : "right";
}

function renderProfile() {
  const p = state.profile;
  bindSegmented($('[data-field="sex_scale"]'), p.sex_scale, (v) => (p.sex_scale = v));
  const feet = $("#feet");
  feet.replaceChildren(...["left", "right"].map((side) => renderFoot(side, p[side])));
  markLonger();
}

function markLonger() {
  const longer = longerSide();
  $$(".foot").forEach((card) => {
    const tag = $(".longer", card);
    if (tag) tag.hidden = card.dataset.side !== longer;
  });
}

function renderFoot(side, foot) {
  const node = $("#foot-template").content.firstElementChild.cloneNode(true);
  node.dataset.side = side;
  const title = $(".foot-title", node);
  title.textContent = `${cap(side)} foot`;
  const tag = Object.assign(document.createElement("span"), { className: "longer", textContent: "Longer" });
  title.append(tag);

  const size = $('[data-k="us_size"]', node);
  size.value = foot.us_size;
  size.setAttribute("aria-label", `${cap(side)} foot US size`);
  size.oninput = () => {
    foot.us_size = parseFloat(size.value);
    markLonger();
  };

  const width = $('[data-k="width"]', node);
  width.setAttribute("aria-label", `${cap(side)} foot width`);
  WIDTHS.forEach((w) => width.add(new Option(w, w, false, w === foot.width)));
  width.onchange = () => (foot.width = width.value);

  const scales = $(".scales", node);
  SCALES.forEach((scale) => {
    const wrap = document.createElement("div");
    wrap.className = "scale";
    const label = Object.assign(document.createElement("span"), { className: "scale-name", textContent: scale.label });
    label.id = `${side}-${scale.key}-label`;
    const group = document.createElement("div");
    group.className = "segmented";
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-labelledby", label.id);
    const options = scale.optional ? [...scale.bands, ""] : scale.bands;
    options.forEach((band) => {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "radio");
      b.dataset.value = band;
      b.textContent = band ? cap(band) : "Not measured";
      group.append(b);
    });
    const currentBand = foot[scale.key] ? foot[scale.key].band : "";
    bindSegmented(group, currentBand, (band) => {
      if (!band) {
        foot[scale.key] = null;
      } else if (!foot[scale.key] || foot[scale.key].band !== band) {
        // Keep the scanned position if the band is unchanged; otherwise use the band's center.
        foot[scale.key] = { band, position: BAND_CENTER[scale.bands.indexOf(band)] };
      }
    });
    wrap.append(label, group);
    scales.append(wrap);
  });
  return node;
}

async function confirmProfile(button) {
  for (const side of ["left", "right"]) {
    const size = Number(state.profile[side].us_size);
    if (!(size > 0)) {
      toast(`Enter a US size for your ${side} foot.`, { error: true });
      return;
    }
  }
  busy(button, true);
  try {
    const userId = await ensureUser();
    await api(`/users/${userId}/profile`, { method: "PUT", json: state.profile });
    show("about");
  } catch (e) {
    toast(e.message, { error: true });
  } finally {
    busy(button, false);
  }
}

/* ---------- About you ---------- */

function setupAbout() {
  const q = state.questionnaire;

  const km = $("#weekly-km");
  const kmOut = $("#weekly-km-out");
  km.oninput = () => {
    q.weekly_km = Number(km.value);
    kmOut.textContent = km.value === "150" ? "150+ km" : `${km.value} km`;
    setFill(km);
  };

  const goals = $("#goals");
  goals.replaceChildren(
    ...GOALS.map((goal) => {
      const chip = Object.assign(document.createElement("button"), { type: "button", className: "chip", textContent: goal });
      chip.setAttribute("aria-pressed", String(q.goals.includes(goal)));
      chip.onclick = () => {
        const on = !q.goals.includes(goal);
        q.goals = on ? [...q.goals, goal] : q.goals.filter((g) => g !== goal);
        chip.setAttribute("aria-pressed", String(on));
      };
      return chip;
    }),
  );

  bindSegmented($('[data-field="feel"]'), q.feel, (v) => (q.feel = v));

  const budget = $("#budget");
  const budgetOut = $("#budget-out");
  const noBudget = $("#no-budget");
  const syncBudget = () => {
    budget.disabled = noBudget.checked;
    q.budget_usd = noBudget.checked ? null : Number(budget.value);
    budgetOut.textContent = noBudget.checked ? "No limit" : `Up to $${budget.value}`;
    setFill(budget);
  };
  budget.oninput = syncBudget;
  noBudget.onchange = syncBudget;

  $$(".tokens").forEach((box) => setupTokens(box, box.dataset.tokens));
  syncAbout();
}

function syncAbout() {
  const q = state.questionnaire;
  const km = $("#weekly-km");
  km.value = q.weekly_km ?? 30;
  km.oninput();
  $$("#goals .chip").forEach((c) => c.setAttribute("aria-pressed", String(q.goals.includes(c.textContent))));
  bindSegmented($('[data-field="feel"]'), q.feel || "balanced", (v) => (q.feel = v));
  $("#no-budget").checked = q.budget_usd == null;
  if (q.budget_usd != null) $("#budget").value = q.budget_usd;
  $("#budget").oninput();
  $$(".tokens").forEach((box) => renderTokens(box, box.dataset.tokens));
}

function setupTokens(box, key) {
  const input = $("input", box);
  const commit = () => {
    const value = input.value.trim().replace(/,$/, "");
    if (value && !state.questionnaire[key].includes(value)) {
      state.questionnaire[key].push(value);
      renderTokens(box, key);
    }
    input.value = "";
  };
  input.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !input.value && state.questionnaire[key].length) {
      state.questionnaire[key].pop();
      renderTokens(box, key);
    }
  };
  input.onblur = commit;
  box.onclick = (e) => e.target === box && input.focus();
}

function renderTokens(box, key) {
  $$(".token", box).forEach((t) => t.remove());
  const input = $("input", box);
  state.questionnaire[key].forEach((name, i) => {
    const token = Object.assign(document.createElement("span"), { className: "token", textContent: name });
    const x = Object.assign(document.createElement("button"), { type: "button", textContent: "✕" });
    x.setAttribute("aria-label", `Remove ${name}`);
    x.onclick = () => {
      state.questionnaire[key].splice(i, 1);
      renderTokens(box, key);
    };
    token.append(x);
    box.insertBefore(token, input);
  });
}

function questionnairePayload() {
  const q = state.questionnaire;
  return {
    weekly_km: q.weekly_km,
    goals: q.goals,
    surface: "road",
    feel: q.feel,
    budget_usd: q.budget_usd,
    loved_shoes: q.loved.map((model) => ({ model })),
    disliked_shoes: q.disliked.map((model) => ({ model })),
  };
}

function loadQuestionnaire(saved) {
  if (!saved) return;
  Object.assign(state.questionnaire, {
    weekly_km: saved.weekly_km ?? 30,
    goals: saved.goals || [],
    feel: saved.feel || "balanced",
    budget_usd: saved.budget_usd ?? null,
    loved: (saved.loved_shoes || []).map((s) => s.model),
    disliked: (saved.disliked_shoes || []).map((s) => s.model),
  });
}

/* ---------- Recommend ---------- */

let pollTimer;
let lineTimer;

async function recommend(button) {
  busy(button, true);
  try {
    const userId = await ensureUser();
    await api(`/users/${userId}/questionnaire`, { method: "PUT", json: questionnairePayload() });
    const task = await api(`/users/${userId}/recommend`, { method: "POST" });
    state.taskId = task.task_id;
    save();
    startWorking();
  } catch (e) {
    toast(e.message, { error: true });
  } finally {
    busy(button, false);
  }
}

function startWorking() {
  show("working");
  let i = 0;
  const line = $("#working-line");
  line.textContent = WORKING_LINES[0];
  clearInterval(lineTimer);
  lineTimer = setInterval(() => {
    i = Math.min(i + 1, WORKING_LINES.length - 1);
    line.style.opacity = "0";
    setTimeout(() => {
      line.textContent = WORKING_LINES[i];
      line.style.opacity = "1";
    }, 300);
  }, 4000);
  poll();
}

function stopWorking() {
  clearInterval(lineTimer);
  clearTimeout(pollTimer);
}

async function poll() {
  try {
    const task = await api(`/tasks/${state.taskId}`);
    if (task.status === "done") {
      stopWorking();
      state.result = task.result;
      renderResults();
      show("results");
      return;
    }
    if (task.status === "failed") {
      stopWorking();
      state.taskId = null;
      save();
      show("about");
      toast(friendlyAiError(task.error || "We couldn't finish your recommendation."), { error: true });
      return;
    }
  } catch (e) {
    if (e.status === 404) {
      stopWorking();
      state.taskId = null;
      save();
      show("about");
      return;
    }
    /* transient network error: keep polling */
  }
  pollTimer = setTimeout(poll, 1500);
}

/* ---------- Results ---------- */

function clean(text) {
  return text.replace(/\s*\[note\s*\d+\]/gi, "").trim();
}

function money(value) {
  if (value == null) return "See price";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value);
}

function renderResults() {
  const rec = state.result;
  $("#results-summary").textContent = rec.summary || "";
  const picks = $("#picks");
  if (!rec.picks.length) {
    picks.replaceChildren(
      Object.assign(document.createElement("p"), {
        className: "lede",
        textContent: "We couldn't find shoes that fit these answers. Try widening your budget or changing the feel.",
      }),
    );
  } else {
    picks.replaceChildren(...rec.picks.map(renderPick));
  }

  const flags = $("#flags");
  flags.hidden = !rec.flags?.length;
  $("ul", flags).replaceChildren(
    ...(rec.flags || []).map((f) => Object.assign(document.createElement("li"), { textContent: f })),
  );

  const disclosure = $("#disclosure");
  disclosure.hidden = !rec.disclosure;
  disclosure.textContent = rec.disclosure || "";
}

function renderPick(pick) {
  const node = $("#pick-template").content.firstElementChild.cloneNode(true);
  $(".pick-rank", node).textContent = pick.rank;
  $(".pick-brand", node).textContent = pick.brand;
  $(".pick-name", node).textContent = `${pick.model} ${pick.version}`;
  $(".size-value", node).textContent = `US ${fmtSize(pick.size.us_size)} · ${widthLabel(pick.size.width)}`;

  const badge = $(".badge", node);
  badge.textContent = pick.size.confident ? "From brand chart" : "Try on first";
  badge.classList.add(pick.size.confident ? "good" : "warn");
  $(".size-basis", node).textContent = [pick.size.basis, pick.size.sizing_note]
    .filter(Boolean)
    .map((s) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`))
    .join(" ");

  const list = (sel, items) =>
    $(sel, node).replaceChildren(
      ...items.map((t) => Object.assign(document.createElement("li"), { textContent: clean(t) })),
    );
  list(".why", pick.why_it_fits);
  list(".watch", pick.watch_for);
  $(".watch-head", node).hidden = !pick.watch_for.length;

  const offers = $(".offers", node);
  if (pick.offers.length) {
    offers.replaceChildren(
      ...pick.offers.map((o) => {
        const a = document.createElement("a");
        a.className = "offer";
        a.href = o.url;
        a.target = "_blank";
        a.rel = "sponsored noopener noreferrer";
        a.innerHTML = `<span><span class="offer-store"></span><br><span class="offer-price"></span></span><span class="offer-buy">Buy</span>`;
        $(".offer-store", a).textContent = o.retailer;
        $(".offer-price", a).textContent = money(o.price_usd);
        a.setAttribute("aria-label", `Buy at ${o.retailer}, ${money(o.price_usd)} (opens in a new tab)`);
        return a;
      }),
    );
  } else {
    offers.className = "no-offers";
    offers.textContent = "Not in stock in your size right now.";
  }

  $('[data-action="feedback"]', node).onclick = () => openSheet(pick);
  return node;
}

/* ---------- Feedback sheet ---------- */

let lastFocus;

function openSheet(pick) {
  state.feedbackPick = pick;
  state.rating = 0;
  lastFocus = document.activeElement;
  $("#sheet-shoe").textContent = `${pick.brand} ${pick.model} ${pick.version} · US ${fmtSize(pick.size.us_size)} ${widthLabel(pick.size.width)}`;
  $("#feedback-notes").value = "";
  paintStars(0);
  $("#sheet-backdrop").hidden = false;
  $("#sheet").hidden = false;
  $("#sheet h2").tabIndex = -1;
  $("#sheet h2").focus();
}

function closeSheet() {
  $("#sheet-backdrop").hidden = true;
  $("#sheet").hidden = true;
  lastFocus?.focus();
}

function paintStars(n) {
  $$("#stars button").forEach((b) => {
    const v = Number(b.dataset.value);
    b.classList.toggle("on", v <= n);
    b.setAttribute("aria-checked", String(v === n));
  });
  $('[data-action="send-feedback"]').disabled = n === 0;
}

function setupSheet() {
  $$("#stars button").forEach((b) => {
    b.onclick = () => {
      state.rating = Number(b.dataset.value);
      paintStars(state.rating);
    };
    b.onmouseenter = () => paintStars(Number(b.dataset.value));
    b.onmouseleave = () => paintStars(state.rating);
  });
  $("#sheet-backdrop").onclick = closeSheet;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#sheet").hidden) closeSheet();
  });
}

async function sendFeedback(button) {
  const pick = state.feedbackPick;
  busy(button, true);
  try {
    await api(`/users/${state.userId}/feedback`, {
      method: "POST",
      json: {
        shoe_id: pick.shoe_id,
        us_size: pick.size.us_size,
        width: pick.size.width,
        rating: state.rating,
        notes: $("#feedback-notes").value.trim() || null,
      },
    });
    closeSheet();
    toast("Thanks. Your next picks will use this.");
  } catch (e) {
    toast(e.message, { error: true });
  } finally {
    busy(button, false);
    paintStars(state.rating);
  }
}

/* ---------- Start over / resume ---------- */

function reset() {
  stopWorking();
  clearSaved();
  Object.assign(state, {
    userId: null,
    taskId: null,
    files: [],
    profile: null,
    result: null,
  });
  state.questionnaire = { weekly_km: 30, goals: [], feel: "balanced", budget_usd: 160, loved: [], disliked: [] };
  renderFiles();
  syncAbout();
  show("welcome");
}

async function resume() {
  const saved = load();
  if (!saved.userId) return;
  try {
    const user = await api(`/users/${saved.userId}`);
    state.userId = user.id;
    state.profile = user.foot_profile;
    loadQuestionnaire(user.questionnaire);
    syncAbout();
    if (state.profile) renderProfile();
  } catch {
    clearSaved();
    return;
  }
  if (!saved.taskId) return;
  try {
    const task = await api(`/tasks/${saved.taskId}`);
    state.taskId = saved.taskId;
    if (task.status === "done") {
      state.result = task.result;
      renderResults();
      show("results", { focus: false });
    } else if (task.status === "queued" || task.status === "running") {
      startWorking();
    }
  } catch {
    state.taskId = null;
    save();
  }
}

/* ---------- Wiring ---------- */

const actions = {
  home: () => show("welcome"),
  start: () => {
    if (state.profile && state.userId) {
      show(state.result ? "results" : "about");
    } else {
      show("scan");
    }
  },
  how: () => $("#how").scrollIntoView({ behavior: "smooth", block: "start" }),
  restart: reset,
  upload: (b) => upload(b),
  manual: () => {
    state.profile = state.profile || { sex_scale: "men", left: blankFoot(), right: blankFoot() };
    renderProfile();
    show("confirm");
  },
  "back-scan": () => show("scan"),
  confirm: (b) => confirmProfile(b),
  "back-confirm": () => {
    if (state.profile) renderProfile();
    show("confirm");
  },
  recommend: (b) => recommend(b),
  rerun: (b) => recommend(b),
  "back-about": () => show("about"),
  "close-sheet": closeSheet,
  "send-feedback": (b) => sendFeedback(b),
};

document.addEventListener("click", (e) => {
  const target = e.target.closest("[data-action]");
  if (!target || target.closest("#pick-template")) return;
  const action = actions[target.dataset.action];
  if (action) action(target);
});

setupDropzone();
setupAbout();
setupSheet();
show("welcome", { focus: false });
checkStatus();
resume();
