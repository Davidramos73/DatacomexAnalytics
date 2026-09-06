/* chatkit — a reusable analyst-chat shell.
 *
 * Everything project-specific (branding, prompts, themes, tabs, widgets,
 * filter options) arrives from GET /api/app-config; nothing in this file
 * names a domain.
 *
 * Exports: boot, mountChat, mountWidgetGrid, registerTab, mountLogin.
 */

/* ---------- tiny dom helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = s => String(s).replace(/</g, "&lt;");
const uid = p => p + "_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

/* ---------- markdown (moved verbatim) ---------- */
// Tiny markdown: **bold**, *italic*, `code`, "- " bullet lists. No links/headers —
// agent prose doesn't need them, and it keeps this safe (only esc()'d text ever
// becomes markup).
export function mdLite(raw) {
  const inline = s => esc(s)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  let html = "", inList = false;
  for (const line of String(raw).split("\n")) {
    const bullet = /^\s*[-*]\s+(.*)/.exec(line);
    if (bullet) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(bullet[1])}</li>`;
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      if (line.trim()) html += `<p>${inline(line)}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

/* ---------- tooltip fix (moved verbatim) ---------- */
// Report/chat cards clip overflow (rounded corners), which also clips an
// ECharts tooltip whenever it would render near an edge (SVG renderer draws
// it inside the chart's own container by default). appendToBody moves the
// tooltip to <body> so it's never cut off.
export function withTooltip(echartsOption) {
  return Object.assign({}, echartsOption, {
    tooltip: Object.assign({ appendToBody: true }, echartsOption.tooltip),
  });
}

/* ---------- the "lumen" theme ---------- */
const DEFAULT_THEME = "lumen";
let chartTheme = DEFAULT_THEME;
const theme = () => chartTheme;
const themeArg = () => (chartTheme === "default" ? null : chartTheme);

/* "lumen" — a custom theme tuned to this app's paper / indigo palette. */
if (typeof echarts !== "undefined") {
  echarts.registerTheme("lumen", {
    color: ["#3a53c9", "#2f8f7a", "#c9772f", "#8a5cd0", "#c94f6d", "#3f8fc9"],
    backgroundColor: "transparent",
    textStyle: { fontFamily: "'IBM Plex Sans', system-ui, sans-serif", color: "#1c1b19" },
    title: { textStyle: { color: "#1c1b19", fontWeight: 600, fontSize: 13 } },
    grid: { left: 8, right: 22, top: 34, bottom: 8, containLabel: true },
    categoryAxis: {
      axisLine: { lineStyle: { color: "#d9d4cc" } },
      axisTick: { show: false },
      axisLabel: { color: "#7b776f" },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#7b776f" },
      nameTextStyle: { color: "#a09b93", align: "left", padding: [0, 0, 4, 0] },
      splitLine: { lineStyle: { color: "rgba(0,0,0,.06)" } },
    },
    line: { smooth: true, symbolSize: 7, lineStyle: { width: 2 } },
    bar: { itemStyle: { borderRadius: [4, 4, 0, 0] } },
    tooltip: {
      backgroundColor: "#fff",
      borderColor: "rgba(0,0,0,.1)",
      borderWidth: 1,
      padding: [7, 10],
      textStyle: { color: "#1c1b19", fontSize: 12 },
    },
    legend: { textStyle: { color: "#7b776f" }, icon: "roundRect", itemWidth: 10, itemHeight: 10 },
  });
}

const THEME_LABELS = {
  lumen: "Lumen", default: "ECharts light", macarons: "Macarons",
  vintage: "Vintage", westeros: "Westeros", roma: "Roma", shine: "Shine",
  walden: "Walden", chalk: "Chalk (dark)", dark: "Dark",
};
const themeLabel = t => THEME_LABELS[t] || (t.charAt(0).toUpperCase() + t.slice(1));

/* ---------- store (localStorage; logic moved verbatim) ---------- */
const MAX_CHATS = 40;          // keep the newest N chats
const MAX_HISTORY_TURNS = 6;   // prior user/assistant turns sent for context

export const store = {
  key: "chatkit:default:v1",
  themes: [],
  chats: [],
  activeId: null,
  collapsed: false,
  theme: DEFAULT_THEME,
  load() {
    try {
      const raw = JSON.parse(localStorage.getItem(this.key) || "{}");
      this.chats = Array.isArray(raw.chats) ? raw.chats : [];
      this.activeId = raw.activeId || null;
      this.collapsed = !!raw.collapsed;
      if (this.themes.includes(raw.theme)) this.theme = raw.theme;
    } catch (e) { this.chats = []; this.activeId = null; }
    if (!this.chats.length) this.newChat(false);
    if (!this.chats.find(c => c.id === this.activeId)) this.activeId = this.chats[0].id;
  },
  save() {
    if (this.chats.length > MAX_CHATS) this.chats = this.chats.slice(0, MAX_CHATS);
    const persist = () => localStorage.setItem(this.key, JSON.stringify({
      chats: this.chats, activeId: this.activeId, collapsed: this.collapsed, theme: this.theme,
    }));
    for (let i = 0; i < MAX_CHATS; i++) {
      try { persist(); return; }
      catch (e) {
        // Quota exceeded (or private mode). Drop the oldest chat and retry.
        if (this.chats.length <= 1) return;
        const dropped = this.chats.pop();
        if (this.activeId === dropped.id) this.activeId = this.chats[0].id;
        this.evicted = (this.evicted || 0) + 1;
      }
    }
  },
  active() { return this.chats.find(c => c.id === this.activeId); },
  newChat(save = true) {
    const c = { id: uid("c"), title: "Nuevo chat", createdAt: Date.now(), updatedAt: Date.now(), messages: [] };
    this.chats.unshift(c);
    this.activeId = c.id;
    if (save) this.save();
    return c;
  },
  remove(id) {
    const idx = this.chats.findIndex(c => c.id === id);
    if (idx < 0) return null;
    const [gone] = this.chats.splice(idx, 1);
    if (!this.chats.length) this.newChat(false);
    if (this.activeId === id) this.activeId = this.chats[Math.min(idx, this.chats.length - 1)].id;
    this.save();
    return { chat: gone, idx };
  },
};

/* ---------- toasts ---------- */
let toastTimer = null;

function toast(text) {
  clearTimeout(toastTimer);
  $(".toast")?.remove();
  const t = el("div", "toast");
  t.appendChild(el("span", null, esc(text)));
  document.body.appendChild(t);
  toastTimer = setTimeout(() => t.remove(), 4000);
}

/* ---------- chart card ---------- */
function buildChartCard({ title, meta, spec }) {
  const card = el("div", "card");
  const head = el("div", "card-head");
  const titleEl = el("div", "card-title"); titleEl.textContent = title; head.appendChild(titleEl);
  const metaEl = el("div", "card-meta"); metaEl.textContent = meta; head.appendChild(metaEl);
  const tabs = el("div", "tabs");
  ["Chart", "Spec", "Data"].forEach((name, i) => {
    const b = el("button", i === 0 ? "on" : null, name);
    b.onclick = () => {
      tabs.querySelectorAll("button").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      show(name);
    };
    tabs.appendChild(b);
  });
  head.appendChild(tabs);
  card.appendChild(head);

  const bodyEl = el("div", "card-body");
  card.appendChild(bodyEl);

  function show(name) {
    if (bodyEl._ro) { bodyEl._ro.disconnect(); bodyEl._ro = null; }
    if (bodyEl._chart) { bodyEl._chart.dispose(); bodyEl._chart = null; }
    bodyEl.innerHTML = "";
    if (name === "Chart") {
      const host = el("div");
      host.style.width = "100%";
      host.style.height = "320px";
      bodyEl.appendChild(host);
      requestAnimationFrame(() => {
        try {
          const inst = echarts.init(host, themeArg(), { renderer: "svg" });
          // Every theme sits on the white card — ignore a theme's own page colour.
          inst.setOption(Object.assign({ backgroundColor: "transparent" }, withTooltip(spec)));
          const ro = new ResizeObserver(() => inst.resize());
          ro.observe(host);
          bodyEl._chart = inst;
          bodyEl._ro = ro;
        } catch (err) {
          bodyEl.innerHTML =
            '<div class="err"><div class="err-title">Render error</div><div class="err-text">'
            + esc(err) + "</div></div>";
        }
      });
    } else if (name === "Spec") {
      bodyEl.appendChild(el("div", "spec-view", esc(JSON.stringify(spec, null, 2))));
    } else {
      // Data tab reads the rows bound into the spec (dataset.source is an
      // array of row objects); no separate copy is stored.
      const src = (spec && spec.dataset && Array.isArray(spec.dataset.source)) ? spec.dataset.source : [];
      const cols = (src.length && !Array.isArray(src[0])) ? Object.keys(src[0]) : [];
      const t = el("table");
      const tr = el("tr");
      cols.forEach(c => { const th = el("th"); th.textContent = c; tr.appendChild(th); });
      t.appendChild(tr);
      src.slice(0, 50).forEach(rowObj => {
        const r = el("tr");
        cols.forEach(c => r.appendChild(el("td", null, esc(rowObj[c]))));
        t.appendChild(r);
      });
      const wrap = el("div"); wrap.style.overflow = "auto"; wrap.appendChild(t);
      if (src.length > 50) wrap.appendChild(el("div", "card-meta", "Showing 50 of " + src.length + " rows"));
      bodyEl.appendChild(wrap);
    }
  }
  // Render once attached so the chart can measure its container.
  requestAnimationFrame(() => show("Chart"));
  return card;
}

/* =====================================================================
 * mountChat
 * ===================================================================== */
export function mountChat(host, cfg = {}) {
  const endpoint = cfg.endpoint || "/api/chat";
  const prompts = cfg.prompts || [];
  store.key = cfg.storageKey || "chatkit:default:v1";
  store.themes = cfg.themes || [];
  const onChats = cfg.onChatsChanged || (() => {});
  const onTitle = cfg.onTitle || (() => {});

  host.innerHTML = `
      <div class="thread"><div class="thread-inner"></div></div>
      <div class="composer">
        <div class="composer-inner">
          <textarea rows="1" placeholder="${esc(cfg.placeholder || "Escribe tu pregunta…")}"></textarea>
          <button class="send">↑</button>
        </div>
        <div class="hint"></div>
      </div>`;

  const thread = $(".thread", host);
  const threadInner = $(".thread-inner", host);
  const draft = $("textarea", host);
  const sendBtn = $(".send", host);
  const hint = $(".hint", host);
  hint.innerHTML = cfg.hintHtml
    || "Respuestas generadas por IA · pueden contener errores, verifica cifras críticas";

  function disposeThreadCharts() {
    threadInner.querySelectorAll(".card-body > div").forEach(d => {
      const inst = echarts.getInstanceByDom(d);
      if (inst) inst.dispose();
    });
  }

  function renderAgentMessage(msg) {
    const wrap = el("div", "agent");
    wrap.appendChild(el("div", "avatar"));
    const body = el("div", "agent-body");
    wrap.appendChild(body);

    if (msg.steps && msg.steps.length) {
      const trace = el("details", "trace");
      trace.appendChild(el("summary", null, msg.steps.length === 1 ? "1 step" : msg.steps.length + " steps"));
      const steps = el("div", "steps");
      msg.steps.forEach(s => {
        const d = el("div");
        d.appendChild(el("div", "step-label", esc(s.label)));
        if (s.detail) d.appendChild(el("div", "step-detail", esc(s.detail)));
        steps.appendChild(d);
      });
      trace.appendChild(steps);
      body.appendChild(trace);
    }
    (msg.paras || []).forEach(t => body.appendChild(el("div", "para", mdLite(t))));
    if (msg.chart) body.appendChild(buildChartCard(msg.chart));
    if (msg.error) {
      const c = el("div", "card");
      const b = el("div", "err");
      b.appendChild(el("div", "err-title", "Spec failed to render"));
      b.appendChild(el("div", "err-text", esc(msg.error)));
      c.appendChild(b);
      body.appendChild(c);
    }
    return wrap;
  }

  function renderThread() {
    disposeThreadCharts();
    threadInner.innerHTML = "";
    const chat = store.active();
    onTitle(chat.title);

    if (!chat.messages.length) {
      const e = el("div", "empty");
      e.appendChild(el("h1", null, esc(cfg.emptyTitle || "¿Qué miramos hoy?")));
      e.appendChild(el("p", null, esc(cfg.emptyText || "Pregunta por evolución, socios comerciales, mix de producto o precios.")));
      const chips = el("div", "chips");
      prompts.forEach(p => {
        const b = el("button", null, esc(p));
        b.onclick = () => { draft.value = p; send(); };
        chips.appendChild(b);
      });
      e.appendChild(chips);
      threadInner.appendChild(e);
      return;
    }
    chat.messages.forEach(m => {
      if (m.role === "user") {
        const n = el("div", "user"); n.textContent = m.text;
        threadInner.appendChild(n);
      } else {
        threadInner.appendChild(renderAgentMessage(m));
      }
    });
    thread.scrollTop = thread.scrollHeight;
  }

  /* ---------- streaming a turn ---------- */
  let busy = false;

  function liveAgentBlock() {
    const wrap = el("div", "agent");
    wrap.appendChild(el("div", "avatar"));
    const body = el("div", "agent-body");
    wrap.appendChild(body);
    threadInner.appendChild(wrap);

    const trace = el("details", "trace");
    trace.appendChild(el("summary", null, "steps"));
    const stepsEl = el("div", "steps");
    trace.appendChild(stepsEl);
    let hasSteps = false;

    const thinking = el("div", "thinking", "<i></i><i></i><i></i><span></span>");
    body.appendChild(thinking);
    let paraEl = null;  // the paragraph currently being streamed into

    return {
      thinking(label) { thinking.querySelector("span").textContent = label; },
      step(label, detail) {
        if (!hasSteps) { body.insertBefore(trace, thinking); hasSteps = true; }
        const s = el("div");
        s.appendChild(el("div", "step-label", esc(label)));
        if (detail) s.appendChild(el("div", "step-detail", esc(detail)));
        stepsEl.appendChild(s);
        trace.querySelector("summary").textContent =
          stepsEl.children.length === 1 ? "1 step" : stepsEl.children.length + " steps";
      },
      delta(t) {
        thinking.remove();
        if (!paraEl) { paraEl = el("div", "para"); body.appendChild(paraEl); }
        paraEl.textContent += t;
      },
      text(t) {
        thinking.remove();
        if (paraEl) { paraEl.innerHTML = mdLite(t); paraEl = null; }
        else body.appendChild(el("div", "para", mdLite(t)));
      },
      error(msg) {
        thinking.remove();
        const c = el("div", "card");
        const b = el("div", "err");
        b.appendChild(el("div", "err-title", "Spec failed to render"));
        b.appendChild(el("div", "err-text", esc(msg)));
        c.appendChild(b);
        body.appendChild(c);
      },
      chart(payload) { thinking.remove(); body.appendChild(buildChartCard(payload)); },
      done() { thinking.remove(); },
    };
  }

  async function send() {
    const text = draft.value.trim();
    if (!text || busy) return;
    busy = true; sendBtn.disabled = true; draft.value = "";

    const chat = store.active();

    // Prior turns for context: user questions + the agent's prose answers.
    const history = [];
    for (const m of chat.messages) {
      if (m.role === "user") history.push({ role: "user", content: m.text });
      else if (m.role === "agent" && m.paras && m.paras.length)
        history.push({ role: "assistant", content: m.paras.join("\n\n") });
    }
    const trimmedHistory = history.slice(-MAX_HISTORY_TURNS);

    chat.messages.push({ role: "user", text });
    if (chat.title === "Nuevo chat") chat.title = text.length > 38 ? text.slice(0, 38) + "…" : text;
    const aMsg = { role: "agent", steps: [], paras: [], chart: null, error: null, time: null };
    chat.messages.push(aMsg);
    chat.updatedAt = Date.now();
    store.save();

    $(".empty", threadInner)?.remove();
    const userNode = el("div", "user"); userNode.textContent = text;
    threadInner.appendChild(userNode);
    onTitle(chat.title);
    onChats();

    const agent = liveAgentBlock();
    agent.thinking("Working…");
    thread.scrollTop = thread.scrollHeight;

    let res;
    try {
      res = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_id: chat.id, message: text, history: trimmedHistory }),
      });
    } catch (e) {
      agent.error("Network error: " + e);
      aMsg.error = "Network error: " + e; store.save();
      busy = false; sendBtn.disabled = false; return;
    }
    if (!res.ok) {
      agent.error("Server error " + res.status);
      aMsg.error = "Server error " + res.status; store.save();
      busy = false; sendBtn.disabled = false; return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop();
      for (const chunk of chunks) {
        const lines = chunk.split("\n");
        const ev = (lines.find(l => l.startsWith("event: ")) || "").slice(7).trim();
        const dataLine = lines.find(l => l.startsWith("data: "));
        if (!ev || !dataLine) continue;
        const d = JSON.parse(dataLine.slice(6));
        if (ev === "thinking") agent.thinking(d.label);
        else if (ev === "step") { agent.step(d.label, d.detail); aMsg.steps.push({ label: d.label, detail: d.detail }); }
        else if (ev === "delta") agent.delta(d.text);
        else if (ev === "text") { agent.text(d.text); aMsg.paras = [d.text]; }
        else if (ev === "chart") { agent.chart(d); aMsg.chart = { title: d.title, meta: d.meta, spec: d.spec }; }
        else if (ev === "error") { agent.error(d.message); aMsg.error = d.message; }
        else if (ev === "done") { agent.done(); aMsg.time = d.seconds; }
        thread.scrollTop = thread.scrollHeight;
      }
    }
    chat.updatedAt = Date.now();
    store.save();
    if (store.evicted) {
      toast("Older chats dropped to free storage space");
      store.evicted = 0;
      onChats();
    }
    busy = false; sendBtn.disabled = false;
  }

  sendBtn.onclick = send;
  draft.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });

  return {
    store,
    renderThread,
    send,
    focus: () => draft.focus(),
    hintEl: hint,
  };
}

/* =====================================================================
 * mountWidgetGrid
 * ===================================================================== */
export function mountWidgetGrid(host, cfg = {}) {
  const basePath = cfg.basePath || "";
  const widgets = cfg.widgets || {};
  const filters = cfg.filters || [];
  const filterOptions = cfg.filterOptions || {};
  const themeOf = typeof cfg.theme === "function" ? cfg.theme : () => (cfg.theme || theme());

  host.innerHTML = '<div class="rp-filters"></div><div class="rp-scroll"><div class="rp-grid"></div></div>';
  const bar = $(".rp-filters", host);
  const grid = $(".rp-grid", host);

  if (cfg.onBack) {
    const back = el("button", "rp-back", "← Volver al chat");
    back.type = "button";
    back.onclick = cfg.onBack;
    bar.appendChild(back);
  }

  const values = {};
  const controls = {};

  function optionLabel(tpl, obj) {
    if (typeof obj !== "object" || obj === null) return String(obj);
    if (!tpl) return String(obj.label ?? obj.value ?? obj.code ?? JSON.stringify(obj));
    return tpl.replace(/\{(\w+)\}/g, (_, k) => obj[k] ?? "");
  }

  for (const p of filters) {
    values[p.name] = p.default ?? "";
    const label = el("label");
    label.appendChild(document.createTextNode(p.ui_label || p.name));

    let control;
    if (p.type === "int") {
      control = el("input");
      control.type = "number";
      if (p.ui_min != null) control.min = p.ui_min;
      if (p.ui_max != null) control.max = p.ui_max;
      if (p.default != null) control.value = p.default;
      control.style.width = "70px";
    } else if (p.ui_options || p.ui_options_from) {
      control = el("select");
      const opts = p.ui_options
        ? p.ui_options.map(o => [String(o.value), String(o.label ?? o.value)])
        : (filterOptions[p.ui_options_from] || []).map(o => {
            const value = (typeof o === "object" && o !== null) ? String(o.value ?? o.code ?? "") : String(o);
            return [value, optionLabel(p.ui_option_label, o)];
          });
      // A non-required param with a default that no option covers still needs a
      // row (e.g. heading "64" = everything) — keep it first.
      if (p.default != null && !opts.some(o => o[0] === String(p.default))) {
        opts.unshift([String(p.default), p.ui_default_label || String(p.default)]);
      }
      opts.forEach(([v, l]) => {
        const o = el("option"); o.value = v; o.textContent = l;
        control.appendChild(o);
      });
      if (p.default != null) control.value = String(p.default);
    } else if (p.enum) {
      control = el("select");
      p.enum.forEach(v => { const o = el("option"); o.value = v; o.textContent = v; control.appendChild(o); });
      if (p.default != null) control.value = String(p.default);
    } else {
      control = el("input");
      control.type = "text";
      if (p.default != null) control.value = p.default;
    }
    control.addEventListener("change", () => { values[p.name] = control.value; load(); });
    values[p.name] = control.value;
    controls[p.name] = control;
    label.appendChild(control);
    bar.appendChild(label);
  }

  const charts = {};

  function urlFor(key, desc) {
    const path = desc.rest_path.startsWith("/") ? desc.rest_path : basePath + desc.rest_path;
    const qs = new URLSearchParams();
    for (const p of desc.params || []) {
      let v = Object.prototype.hasOwnProperty.call(values, p.name) ? values[p.name] : p.default;
      if (v === undefined || v === null || v === "") {
        if (p.required && p.default != null) v = p.default; else continue;
      }
      qs.set(p.name, v);
    }
    const q = qs.toString();
    return q ? path + "?" + q : path;
  }

  async function load() {
    Object.values(charts).forEach(c => c.dispose());
    for (const k in charts) delete charts[k];
    grid.innerHTML = "";

    for (const [key, desc] of Object.entries(widgets)) {
      const card = el("div", "rp-card" + (desc.span === "half" ? " half" : ""));
      grid.appendChild(card);
      try {
        const spec = await fetch(urlFor(key, desc)).then(r => r.json());
        const head = el("div", "rp-card-head");
        head.appendChild(el("div", "rp-card-title", esc(spec.title || key)));
        const kpis = el("div", "rp-kpis");
        (spec.kpis || []).forEach(k =>
          kpis.appendChild(el("span", "rp-kpi " + (k.tone || ""), esc(`${k.label}: ${k.value}`))));
        if (kpis.children.length) head.appendChild(kpis);
        card.appendChild(head);

        const chartHost = el("div", "rp-chart");
        card.appendChild(chartHost);
        const m = spec.meta || {};
        card.appendChild(el("div", "rp-meta",
          esc([m.unit && "unidad " + m.unit, m.granularity, m.is_provisional && "· datos provisionales"]
            .filter(Boolean).join(" "))));

        const t = themeOf();
        const inst = echarts.init(chartHost, t === "default" ? null : t, { renderer: "svg" });
        inst.setOption(Object.assign({ backgroundColor: "transparent" }, withTooltip(spec.echarts)));
        new ResizeObserver(() => inst.resize()).observe(chartHost);
        charts[key] = inst;
      } catch (e) {
        card.appendChild(el("div", "rp-err", esc(`No se pudo cargar «${key}»: ${e}`)));
      }
    }
  }

  return { load, values, controls };
}

/* =====================================================================
 * registerTab
 * ===================================================================== */
const tabRegistry = new Map();

export function registerTab(id, mountFn) {
  tabRegistry.set(id, mountFn);
}

/* ---------- icons ---------- */
const ICONS = {
  bars: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><line x1="3" y1="13" x2="13" y2="13"></line><rect x="3.5" y="7" width="2.6" height="4"></rect><rect x="9.4" y="4" width="2.6" height="7"></rect></svg>',
  plus: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"></line><line x1="3" y1="8" x2="13" y2="8"></line></svg>',
  panel: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="2" y="3" width="12" height="10" rx="2"></rect><line x1="6.5" y1="3" x2="6.5" y2="13"></line></svg>',
  search: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="#8b8781" stroke-width="1.5" stroke-linecap="round"><circle cx="7" cy="7" r="4.2"></circle><line x1="10.2" y1="10.2" x2="13.5" y2="13.5"></line></svg>',
  dots: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><circle cx="4" cy="8" r="1.35"></circle><circle cx="8" cy="8" r="1.35"></circle><circle cx="12" cy="8" r="1.35"></circle></svg>',
  chevron: '<svg class="sb-user-chev" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>',
  logout: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 14H3V2h3M10.5 11l3-3-3-3M13.5 8H6"/></svg>',
};
const icon = name => ICONS[name] || ICONS.bars;

/* =====================================================================
 * boot
 * ===================================================================== */
export async function boot(opts = {}) {
  let user;
  try {
    const r = await fetch("/auth/me");
    if (!r.ok) { location.href = "/login.html"; return; }
    user = await r.json();
  } catch (e) { location.href = "/login.html"; return; }

  const config = await fetch("/api/app-config").then(r => r.json());
  const branding = config.branding || {};
  const themes = config.echarts_themes || [DEFAULT_THEME];
  const tabs = config.tabs || [];
  const allWidgets = config.widgets || {};
  const filterOptions = config.filter_options || {};

  if (branding.name) document.title = branding.name;

  const root = opts.root || document.getElementById("app");
  root.innerHTML = `
<div class="app">
  <aside class="sidebar">
    <div class="sb-top">
      <div class="sb-logo"><i></i></div>
      <div class="sb-name"></div>
      <button class="icon-btn" data-role="collapse" title="Toggle sidebar">${icon("panel")}</button>
    </div>
    <div class="sb-actions">
      <div class="sb-tabs"></div>
      <button class="new-chat" data-role="new-chat">${icon("plus")}<span class="nc-label">Nuevo chat</span></button>
      <div class="search sb-hideable">${icon("search")}<input data-role="search" placeholder="Buscar chats" autocomplete="off"></div>
    </div>
    <div class="sb-list sb-hideable" data-role="chat-list"></div>
    <div class="sb-note sb-hideable">Guardado en este navegador</div>
    <div class="sb-user" data-role="user"></div>
  </aside>
  <main>
    <header>
      <div class="title" data-role="header-title">Nuevo chat</div>
      <div class="badge"><span></span></div>
      <div class="grow"></div>
      <select class="theme-sel" data-role="theme" title="Tema del gráfico"></select>
      <div class="engine">echarts v5</div>
    </header>
    <div class="ck-view" data-role="chat-view"></div>
  </main>
</div>`;

  const sidebar = $(".sidebar", root);
  const sbName = $(".sb-name", root);
  const sbTabs = $(".sb-tabs", root);
  const chatList = $('[data-role="chat-list"]', root);
  const searchInput = $('[data-role="search"]', root);
  const headerTitle = $('[data-role="header-title"]', root);
  const badge = $(".badge", root);
  const themeSel = $('[data-role="theme"]', root);
  const chatView = $('[data-role="chat-view"]', root);
  const tabViews = $("main", root);
  const userHost = $('[data-role="user"]', root);

  sbName.textContent = branding.short_name || branding.name || "chatkit";
  badge.appendChild(document.createTextNode(branding.badge || ""));

  /* ---------- theme selector ---------- */
  themes.forEach(t => {
    const o = document.createElement("option");
    o.value = t; o.textContent = themeLabel(t);
    themeSel.appendChild(o);
  });

  /* ---------- tabs ---------- */
  const navBtns = {};
  const views = {};
  const mounts = {};

  for (const tab of tabs) {
    const b = el("button", "sb-nav");
    b.title = tab.label;
    b.innerHTML = icon(tab.icon) + `<span class="nc-label">${esc(tab.label)}</span>`;
    b.onclick = () => setView(tab.id);
    sbTabs.appendChild(b);
    navBtns[tab.id] = b;

    const v = el("div", "ck-view");
    v.hidden = true;
    tabViews.appendChild(v);
    views[tab.id] = v;
  }

  let current = "chat";

  function setView(id) {
    current = id;
    chatView.hidden = id !== "chat";
    themeSel.hidden = id !== "chat";
    for (const tab of tabs) {
      views[tab.id].hidden = tab.id !== id;
      navBtns[tab.id].classList.toggle("active", tab.id === id);
    }
    const tab = tabs.find(t => t.id === id);
    headerTitle.textContent = tab ? tab.label : store.active().title;
    if (!tab) return;

    if (!mounts[tab.id]) {
      if (tab.kind === "widget_grid") {
        const picked = {};
        (tab.widgets || []).forEach(k => { if (allWidgets[k]) picked[k] = allWidgets[k]; });
        // A tab names its filters by param name; the descriptors live on the
        // widgets that declare them.
        const byName = {};
        for (const d of Object.values(allWidgets)) {
          for (const p of d.params || []) if (!byName[p.name]) byName[p.name] = p;
        }
        const filters = (tab.filters || []).map(f => (typeof f === "string" ? byName[f] : f)).filter(Boolean);
        mounts[tab.id] = mountWidgetGrid(views[tab.id], {
          basePath: opts.basePath || "",
          widgets: picked,
          filters,
          filterOptions,
          theme,
          onBack: () => setView("chat"),
        });
      } else {
        const fn = tabRegistry.get(tab.id);
        if (!fn) {
          views[tab.id].appendChild(el("div", "rp-err", `Sin vista registrada para «${esc(tab.id)}»`));
          mounts[tab.id] = { load: () => {} };
        } else {
          mounts[tab.id] = fn(views[tab.id], { config, tab, theme }) || { load: () => {} };
        }
      }
    }
    if (mounts[tab.id].load) mounts[tab.id].load();
  }

  /* ---------- chat ---------- */
  const firstTab = tabs[0];
  // UI copy: the domain's /api/app-config `copy` block wins, then boot(opts),
  // then a generic default so any project renders something sensible.
  const copy = config.copy || {};
  const hintHtml = copy.hint_html || opts.hintHtml
    || ("Respuestas generadas por IA a partir de datos oficiales"
      + (branding.badge ? " (" + esc(branding.badge) + ")" : "")
      + " · pueden contener errores, verifica cifras críticas"
      + (firstTab ? ' · <a href="#" data-role="hint-tab">ver ' + esc(firstTab.label.toLowerCase()) + "</a>" : ""));

  const chat = mountChat(chatView, {
    endpoint: opts.endpoint || "/api/chat",
    prompts: config.example_prompts || [],
    storageKey: opts.storageKey || "lumen.v1",
    themes,
    placeholder: copy.placeholder || opts.placeholder || "Escribe tu pregunta…",
    emptyTitle: copy.empty_title || opts.emptyTitle || "¿Qué miramos hoy?",
    emptyText: copy.empty_text || opts.emptyText,
    hintHtml,
    onTitle: t => { if (current === "chat") headerTitle.textContent = t; },
    onChatsChanged: () => renderSidebar(),
  });

  const hintLink = $('[data-role="hint-tab"]', chatView);
  if (hintLink && firstTab) hintLink.onclick = e => { e.preventDefault(); setView(firstTab.id); };

  /* ---------- sidebar rendering ---------- */
  let openMenuId = null;
  let renamingId = null;

  function renderSidebar() {
    sidebar.classList.toggle("collapsed", store.collapsed);
    const q = searchInput.value.trim().toLowerCase();
    chatList.innerHTML = "";
    chatList.appendChild(el("div", "sb-section", "Recent"));

    const rows = store.chats.filter(c => !q || c.title.toLowerCase().includes(q));
    if (!rows.length) {
      chatList.appendChild(el("div", "sb-section", q ? "No matches" : "No chats"));
    }
    rows.forEach(c => {
      const row = el("div", "chat-row" + (c.id === store.activeId ? " active" : ""));

      if (renamingId === c.id) {
        const input = el("input", "rename");
        input.value = c.title;
        const commit = () => {
          const v = input.value.trim();
          if (v) { c.title = v; c.updatedAt = Date.now(); store.save(); }
          renamingId = null;
          renderSidebar(); chat.renderThread();
        };
        input.onkeydown = e => {
          if (e.key === "Enter") commit();
          else if (e.key === "Escape") { renamingId = null; renderSidebar(); }
        };
        input.onblur = commit;
        row.appendChild(input);
        chatList.appendChild(row);
        setTimeout(() => { input.focus(); input.select(); }, 0);
        return;
      }

      const sel = el("button", "sel"); sel.textContent = c.title;
      sel.onclick = () => {
        setView("chat");
        if (store.activeId === c.id) return;
        store.activeId = c.id; store.save();
        openMenuId = null;
        renderSidebar(); chat.renderThread();
      };
      row.appendChild(sel);

      const menuBtn = el("button", "menu-btn" + (openMenuId === c.id ? " open" : ""), icon("dots"));
      menuBtn.onclick = e => {
        e.stopPropagation();
        openMenuId = openMenuId === c.id ? null : c.id;
        renderSidebar();
      };
      row.appendChild(menuBtn);

      if (openMenuId === c.id) {
        const pop = el("div", "menu-pop");
        const rename = el("button", null, "Rename");
        rename.onclick = e => { e.stopPropagation(); openMenuId = null; renamingId = c.id; renderSidebar(); };
        const del = el("button", "danger", "Delete chat");
        del.onclick = e => { e.stopPropagation(); openMenuId = null; renderSidebar(); askDelete(c); };
        pop.appendChild(rename); pop.appendChild(del);
        row.appendChild(pop);
      }
      chatList.appendChild(row);
    });
  }

  document.addEventListener("click", e => {
    if (openMenuId && !e.target.closest(".chat-row")) { openMenuId = null; renderSidebar(); }
  });

  /* ---------- delete confirm + undo toast ---------- */
  function askDelete(target) {
    const overlay = el("div", "overlay");
    const dialog = el("div", "dialog");
    dialog.appendChild(el("h3", null, "Delete chat?"));
    dialog.appendChild(el("p", null, esc("“" + target.title + "” and its charts will be removed. This can’t be undone.")));
    const row = el("div", "row");
    const cancel = el("button", "cancel", "Cancel");
    cancel.onclick = () => overlay.remove();
    const confirm = el("button", "confirm", "Delete");
    confirm.onclick = () => {
      overlay.remove();
      const trash = store.remove(target.id);
      renderSidebar(); chat.renderThread();
      if (trash) showUndo(trash);
    };
    row.appendChild(cancel); row.appendChild(confirm);
    dialog.appendChild(row);
    overlay.appendChild(dialog);
    overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  }

  function showUndo(trash) {
    clearTimeout(toastTimer);
    $(".toast")?.remove();
    const t = el("div", "toast");
    t.appendChild(el("span", null, "Chat deleted"));
    const undo = el("button", null, "Undo");
    undo.onclick = () => {
      clearTimeout(toastTimer);
      t.remove();
      store.chats.splice(Math.min(trash.idx, store.chats.length), 0, trash.chat);
      store.activeId = trash.chat.id;
      store.save();
      renderSidebar(); chat.renderThread();
    };
    t.appendChild(undo);
    document.body.appendChild(t);
    toastTimer = setTimeout(() => t.remove(), 5000);
  }

  /* ---------- wiring ---------- */
  $('[data-role="new-chat"]', root).onclick = () => {
    setView("chat");
    const c = store.active();
    if (c.messages.length === 0) { chat.focus(); return; }
    store.newChat();
    searchInput.value = "";
    renderSidebar(); chat.renderThread();
    chat.focus();
  };
  $('[data-role="collapse"]', root).onclick = () => {
    store.collapsed = !store.collapsed; store.save();
    renderSidebar();
  };
  searchInput.addEventListener("input", renderSidebar);

  themeSel.addEventListener("change", () => {
    store.theme = themeSel.value;
    chartTheme = store.theme;
    store.save();
    chat.renderThread();
    for (const id in mounts) if (!views[id].hidden && mounts[id].load) mounts[id].load();
  });

  /* ---------- user avatar + menu ---------- */
  function userInitials(u) {
    const src = (u.name || u.email || "?").trim();
    const parts = src.split(/[\s@._-]+/).filter(Boolean);
    const letters = parts.length >= 2
      ? parts[0][0] + parts[1][0]
      : src.slice(0, 2);
    return letters.toUpperCase();
  }

  let userMenuOpen = false;

  function renderUser(u) {
    userHost.classList.toggle("open", userMenuOpen);
    userHost.innerHTML = "";

    const row = el("button", "sb-user-row");
    row.title = u.email || "";
    row.appendChild(el("div", "sb-avatar", esc(userInitials(u))));
    row.appendChild(el("div", "sb-user-name", esc(u.name || u.email)));
    row.innerHTML += icon("chevron");
    row.onclick = e => { e.stopPropagation(); userMenuOpen = !userMenuOpen; renderUser(u); };
    userHost.appendChild(row);

    if (userMenuOpen) {
      const pop = el("div", "sb-user-pop");
      const head = el("div", "head");
      head.appendChild(el("b", null, esc(u.name || u.email)));
      if (u.name) head.appendChild(el("span", null, esc(u.email)));
      pop.appendChild(head);
      const out = el("button", null, icon("logout") + "Cerrar sesión");
      out.onclick = async e => {
        e.stopPropagation();
        try { await fetch("/auth/logout", { method: "POST" }); } catch (err) {}
        location.href = "/login.html";
      };
      pop.appendChild(out);
      userHost.appendChild(pop);
    }
  }

  const closeUserMenu = () => {
    if (!userMenuOpen) return;
    userMenuOpen = false;
    userHost.classList.remove("open");
    userHost.querySelector(".sb-user-pop")?.remove();
  };
  document.addEventListener("click", e => {
    if (userMenuOpen && !e.target.closest('[data-role="user"]')) closeUserMenu();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeUserMenu();
  });

  /* ---------- go ---------- */
  renderUser(user);
  store.load();
  chartTheme = store.theme;
  themeSel.value = store.theme;
  renderSidebar();
  chat.renderThread();
  setView("chat");

  return { store, chat, setView, config };
}

/* =====================================================================
 * mountLogin
 * ===================================================================== */
export async function mountLogin(host) {
  host = host || document.getElementById("app") || document.body;
  host.innerHTML = `
<div class="card">
  <div class="logo"><i></i></div>
  <h1></h1>
  <p>Acceso restringido.</p>
  <div id="gbtn"></div>
  <div class="err" data-role="err" hidden></div>
  <div class="foot">Inicia sesión con tu cuenta de Google autorizada. Al acceder
    registramos tu email y la fecha de acceso, solo para control de uso.</div>
</div>`;

  const err = $('[data-role="err"]', host);
  const gbtn = $("#gbtn", host);
  const showErr = msg => { err.textContent = msg; err.hidden = false; };

  async function onCredential(resp) {
    err.hidden = true;
    try {
      const r = await fetch("/auth/google", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ credential: resp.credential }),
      });
      if (r.ok) { location.href = "/"; return; }
      if (r.status === 403) showErr("Tu cuenta no está autorizada. Contacta al administrador.");
      else showErr("No se pudo iniciar sesión (" + r.status + ").");
    } catch (e) {
      showErr("Error de red: " + e);
    }
  }

  let cfg;
  try { cfg = await fetch("/api/app-config").then(r => r.json()); }
  catch (e) { showErr("No se pudo cargar la configuración."); return; }

  const branding = cfg.branding || {};
  const auth = cfg.auth || {};
  $("h1", host).textContent = branding.name || "Acceder";
  if (branding.name) document.title = "Acceder · " + branding.name;
  if (branding.badge) $("p", host).textContent = branding.badge + " · Acceso restringido.";

  if (!auth.enabled) { location.href = "/"; return; }
  if (!auth.client_id) { showErr("Login no configurado (falta GOOGLE_CLIENT_ID)."); return; }

  const start = () => {
    if (!window.google?.accounts?.id) return setTimeout(start, 100);
    google.accounts.id.initialize({ client_id: auth.client_id, callback: onCredential });
    google.accounts.id.renderButton(gbtn, {
      theme: "outline", size: "large", text: "signin_with", locale: "es",
    });
  };
  start();
}
