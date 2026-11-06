"use strict";

/* Centro de control de batonAI.
   La vista no habla con el gateway: llama al puente Python de pywebview.
   Sin pywebview (por ejemplo, abierto en un navegador) usa datos de ejemplo. */

const LOGO_PATHS = {
  anthropic:
    "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z",
  openai:
    "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z",
  antigravity:
    "M89.6992 93.695C94.3659 97.195 101.366 94.8617 94.9492 88.445C75.6992 69.7783 79.7825 18.445 55.8659 18.445C31.9492 18.445 36.0325 69.7783 16.7825 88.445C9.78251 95.445 17.3658 97.195 22.0325 93.695C40.1159 81.445 38.9492 59.8617 55.8659 59.8617C72.7825 59.8617 71.6159 81.445 89.6992 93.695Z",
  gemini:
    "M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81",
  github:
    "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
};

const MOCK_AGENTS = [
  {
    id: "claude-code",
    name: "Auth refactor",
    provider: "anthropic",
    model: "claude-sonnet-4-5",
    status: "running",
    cwd: "C:\\dev\\baton-demo",
    task: "Migrar el login a passkeys",
    log_tail: ["Leyendo src/auth/session.ts", "Editando 3 archivos", "Ejecutando tests…"],
    cost_session: 0.42,
    tokens_session: 18400,
    last_event_at: new Date().toISOString(),
    since: new Date(Date.now() - 240_000).toISOString(),
  },
  {
    id: "codex",
    name: "API parser",
    provider: "openai",
    model: "gpt-5-codex",
    status: "waiting_input",
    cwd: "C:\\dev\\baton-api",
    task: "Revisar el parser de eventos",
    log_tail: ["Quiere ejecutar: npm test -- --coverage"],
    cost_session: 0.18,
    tokens_session: 7200,
    last_event_at: new Date().toISOString(),
    since: new Date(Date.now() - 600_000).toISOString(),
    approval_id: "apr_demo",
    prompt: "npm test -- --coverage",
    risk: "normal",
  },
  {
    id: "antigravity",
    name: "Landing page",
    provider: "antigravity",
    model: "gemini-3-pro",
    status: "idle",
    cwd: "C:\\dev\\baton-web",
    task: "Esperando la siguiente instrucción",
    log_tail: ["Build completado en 4,2 s"],
    cost_session: 0.07,
    tokens_session: 3100,
    last_event_at: new Date(Date.now() - 900_000).toISOString(),
    since: new Date(Date.now() - 900_000).toISOString(),
  },
  {
    id: "gemini",
    name: "Docs review",
    provider: "google",
    model: "gemini-3-pro",
    status: "done",
    cwd: "C:\\dev\\baton-docs",
    task: "Revisar el README",
    log_tail: ["3 sugerencias aplicadas"],
    cost_session: 0.03,
    tokens_session: 1200,
    last_event_at: new Date(Date.now() - 1800_000).toISOString(),
    since: new Date(Date.now() - 1800_000).toISOString(),
  },
  {
    id: "copilot",
    name: "PR fix",
    provider: "github",
    model: "gpt-5",
    status: "error",
    cwd: "C:\\dev\\baton-pr",
    task: "Arreglar el conflicto de merge",
    log_tail: ["Error: conflicto en package-lock.json"],
    cost_session: 0.02,
    tokens_session: 800,
    last_event_at: new Date(Date.now() - 2400_000).toISOString(),
    since: new Date(Date.now() - 2400_000).toISOString(),
  },
  {
    id: "cursor",
    name: "UI polish",
    provider: "cursor",
    model: "cursor",
    status: "offline",
    cwd: "C:\\dev\\baton-ui",
    task: "Ajustar el espaciado",
    log_tail: [],
    cost_session: 0,
    tokens_session: 0,
    last_event_at: new Date(Date.now() - 7200_000).toISOString(),
    since: new Date(Date.now() - 7200_000).toISOString(),
  },
];

const STATUS_META = {
  waiting_input: { label: "esperando", tone: "wait", rank: 0 },
  error: { label: "error", tone: "off", rank: 1 },
  running: { label: "trabajando", tone: "run", rank: 2 },
  done: { label: "terminado", tone: "on", rank: 3 },
  idle: { label: "en espera", tone: "muted", rank: 4 },
  offline: { label: "desconectado", tone: "off", rank: 5 },
};

const RISK_LABELS = {
  low: "bajo",
  normal: "normal",
  high: "alto",
  critical: "crítico",
};

const state = {
  api: null,
  preview: false,
  view: "agents",
  gateway: "",
  hostname: "",
  agents: [],
  system: {},
  hidden: new Set(),
  pinned: [],
  filters: { query: "", status: "all", provider: "all", sort: "status" },
  detailId: null,
  drawerDraft: "",
  lastStatuses: new Map(),
  info: null,
  devices: [],
  virtualDevice: null,
  virtualPairId: null,
  virtualPoll: null,
  restDirty: false,
  connection: { url: "", token: "", remote: null },
  pairingGateway: null,
  discoveredGateways: [],
  limitsView: "remaining",
  limits: {
    ok: false,
    providers: [],
    period: "all",
    view: "remaining",
    selected_windows: null,
    error: null,
    read_at: null,
  },
  audit: { approvals: [], events: [] },
};

const REFRESH_MS = 10000;

const VIEWS = {
  agents: {
    title: "Configuración de agentes",
    lede: "Elige qué agentes se muestran en el hardware. Los ocultos siguen trabajando.",
  },
  hardware: {
    title: "Hardware",
    lede: "Emparejamiento, panel y dispositivos conectados al gateway.",
  },
  audit: {
    title: "Auditoría",
    lede: "Últimas aprobaciones y eventos registrados por el gateway.",
  },
  settings: {
    title: "Ajustes",
    lede: "Gateway, límites de las IAs y descubrimiento de agentes.",
  },
};

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function logoSvg(agent) {
  const key = (agent.provider || "").toLowerCase();
  if (key === "anthropic" || key === "claude") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#D97757" d="${LOGO_PATHS.anthropic}"/></svg>`;
  }
  if (key === "openai" || key === "codex") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#ece9df" d="${LOGO_PATHS.openai}"/></svg>`;
  }
  if (key === "google" || key === "gemini") {
    const id = `gem-${String(agent.id).replace(/[^a-zA-Z0-9_-]/g, "")}`;
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4C8DF6"/><stop offset=".5" stop-color="#9B72CB"/><stop offset="1" stop-color="#D96570"/></linearGradient></defs><path fill="url(#${id})" d="${LOGO_PATHS.gemini}"/></svg>`;
  }
  if (key === "antigravity") {
    const id = `agy-${String(agent.id).replace(/[^a-zA-Z0-9_-]/g, "")}`;
    return `<svg viewBox="0 0 136 136" aria-hidden="true"><defs><linearGradient id="${id}" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#3186FF"/><stop offset=".55" stop-color="#9B72CB"/><stop offset="1" stop-color="#FBBC04"/></linearGradient></defs><path fill="url(#${id})" d="${LOGO_PATHS.antigravity}"/></svg>`;
  }
  if (key === "opencode" || key.startsWith("opencode")) {
    return `<svg viewBox="0 0 512 512" aria-hidden="true"><rect width="512" height="512" rx="72" fill="#131010"/><path d="M320 224V352H192V224H320Z" fill="#5A5858"/><path fill-rule="evenodd" clip-rule="evenodd" d="M384 416H128V96H384V416ZM320 160H192V352H320V160Z" fill="#FFFFFF"/></svg>`;
  }
  if (key === "github" || key === "copilot") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#E6E6E6" d="${LOGO_PATHS.github}"/></svg>`;
  }
  if (key === "cursor") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#E6E6E6" d="M4.2 3.1 20.4 12l-6.9 1.8-3.2 6.6-6.1-17.3Z"/><path fill="#111" d="m8.2 7.9 6.4 3.5-2.7.7-1.3 2.6-2.4-6.8Z" opacity=".55"/></svg>`;
  }
  const initial = (agent.name || "?").charAt(0).toUpperCase();
  return `<span class="logo-initial">${initial}</span>`;
}

function logoNode(agent) {
  const node = el("span", "logo");
  node.innerHTML = logoSvg(agent);
  return node;
}

function eyeIcon(visible) {
  if (visible) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.6"/></svg>`;
  }
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 6.1A10 10 0 0 1 12 6c6 0 9.5 6 9.5 6a15.5 15.5 0 0 1-3.4 3.9"/><path d="M6.3 6.8C3.8 8.4 2.5 12 2.5 12s3.5 6 9.5 6a10.6 10.6 0 0 0 4.1-.8"/></svg>`;
}

function pinIcon(pinned) {
  return `<svg viewBox="0 0 24 24" fill="${pinned ? "currentColor" : "none"}" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 5 3 3v2H7v-2l3-3-1-5Z"/><path d="M12 13v8"/></svg>`;
}

async function getApi() {
  if (window.pywebview && window.pywebview.api) return window.pywebview.api;
  return new Promise((resolve) => {
    let settled = false;
    const done = (api) => {
      if (settled) return;
      settled = true;
      resolve(api);
    };
    window.addEventListener("pywebviewready", () => done(window.pywebview.api), { once: true });
    setTimeout(() => done(null), 900);
  });
}

function mockApi() {
  const hidden = new Set();
  const pinned = [];
  return {
    async gateway_status() {
      return { ok: true, gateway: "vista previa", version: "mock", hostname: "DESKTOP-DEMO" };
    },
    async list_agents() {
      return {
        ok: true,
        agents: MOCK_AGENTS.map((agent) => ({ ...agent })),
        system: {
          total_cost: 0.72,
          total_tokens: 30700,
          active_agents: 2,
          waiting_agents: 1,
        },
        hidden: [...hidden],
        pinned: [...pinned],
        persisted: false,
      };
    },
    async set_visibility(agentId, isHidden) {
      if (isHidden) hidden.add(agentId);
      else hidden.delete(agentId);
      return { ok: true, hidden: [...hidden], persisted: false };
    },
    async set_pinned(agentId, isPinned) {
      const index = pinned.indexOf(agentId);
      if (isPinned && index === -1) {
        if (pinned.length >= 2) return { ok: false, error: "pin_limit" };
        pinned.push(agentId);
      } else if (!isPinned && index !== -1) {
        pinned.splice(index, 1);
      }
      return { ok: true, pinned: [...pinned], persisted: false };
    },
    async gateway_info() {
      return {
        ok: true,
        gateway: "vista previa",
        version: "mock",
        opencode_enabled: true,
        local_agents_enabled: true,
        max_pinned: 2,
        rest_after_s: 300,
        ticker_period: "all",
        ticker_providers: null,
        ticker_windows: null,
        limits_view: "remaining",
        approval_timeout_s: 60,
        heartbeat_s: 10,
        fake_autostart: false,
        dev_mode: true,
        opencode_recency_s: 21600,
        opencode_max_sessions: 8,
        opencode_poll_s: 5,
        local_agents_recency_s: 43200,
        local_agents_max_sessions: 8,
        local_agents_poll_s: 10,
        local_agents_active_s: 120,
        agents: MOCK_AGENTS.length,
        connected_devices: 2,
        hidden_agents: [...hidden],
        pinned_agents: [...pinned],
        sources: [
          { id: "opencode", label: "OpenCode", enabled: true },
          { id: "anthropic", label: "Claude Code", enabled: true },
          { id: "openai", label: "Codex", enabled: true },
          { id: "google", label: "Gemini", enabled: true },
          { id: "antigravity", label: "Antigravity", enabled: true },
          { id: "cursor", label: "Cursor", enabled: true },
          { id: "github", label: "GitHub Copilot", enabled: true },
        ],
      };
    },
    async pairing_code() {
      return { ok: true, code: "428913" };
    },
    async rest_config() {
      return { ok: true, rest_after_s: 300 };
    },
    async set_rest_config(seconds) {
      return { ok: true, rest_after_s: Number(seconds) || 0 };
    },
    async connection_config() {
      return {
        ok: true,
        gateway_url: "http://127.0.0.1:8770",
        token: "",
      };
    },
    async set_connection_config(gateway_url, token) {
      return { ok: true, gateway_url, token };
    },
    async remote_config() {
      return {
        ok: true,
        token: "demo-remote-token",
        url: "http://192.168.0.26:8770",
        urls: [
          { interface: "Wi-Fi", url: "http://192.168.0.26:8770" },
          { interface: "Ethernet 2", url: "http://192.168.56.1:8770" },
        ],
        lan: true,
      };
    },
    async discover_gateways() {
      return {
        ok: true,
        gateways: [
          {
            url: "http://192.168.0.26:8770",
            urls: ["http://192.168.0.26:8770"],
            hostname: "DESKTOP-DEMO",
            device_id: "baton-demo",
            local: false,
          },
        ],
      };
    },
    async pair_control(gateway_url, code) {
      return { ok: true, gateway_url, hostname: "DESKTOP-DEMO" };
    },
    async limits() {
      const now = Math.floor(Date.now() / 1000);
      const readAt = new Date().toISOString();
      return {
        ok: true,
        period: "all",
        view: "remaining",
        selected_windows: null,
        providers: [
          {
            id: "opencode",
            label: "OpenCode",
            installed: true,
            ok: true,
            plan: "Go",
            workspace: "Personal",
            selected: true,
            error: null,
            read_at: readAt,
            budgets: [],
            windows: [
              {
                key: "opencode:rolling",
                id: "rolling",
                label: "Rolling",
                used_percent: 11,
                remaining_percent: 89,
                selected: true,
                resets_at: now + 4 * 3600,
                duration_minutes: 300,
              },
              {
                key: "opencode:weekly",
                id: "weekly",
                label: "Semanal",
                used_percent: 13,
                remaining_percent: 87,
                selected: true,
                resets_at: now + 3 * 86400,
                duration_minutes: 10_080,
              },
              {
                key: "opencode:monthly",
                id: "monthly",
                label: "Mensual",
                used_percent: 20,
                remaining_percent: 80,
                selected: true,
                resets_at: now + 21 * 86400,
                duration_minutes: 43_200,
              },
            ],
          },
          {
            id: "codex",
            label: "Codex",
            installed: true,
            ok: true,
            plan: "free",
            workspace: null,
            selected: true,
            error: null,
            read_at: readAt,
            budgets: [],
            windows: [
              {
                key: "codex:monthly",
                id: "monthly",
                label: "Mensual",
                used_percent: 0,
                remaining_percent: 100,
                selected: true,
                resets_at: now + 29 * 86400,
                duration_minutes: 43_200,
              },
            ],
          },
          {
            id: "claude",
            label: "Claude Code",
            installed: false,
            ok: false,
            plan: null,
            workspace: null,
            selected: false,
            error: "not_installed",
            read_at: null,
            budgets: [],
            windows: [],
          },
        ],
      };
    },
    async set_limit_windows(windows) {
      return { ok: true, selected_windows: windows };
    },
    async set_limits_view(view) {
      return { ok: true, limits_view: view };
    },
    async virtual_device() {
      return {
        ok: true,
        device_id: "baton-demo",
        short: "DEMO",
        name: "Dispositivo virtual",
        paired: false,
        paired_to: null,
        paired_at: null,
        sas: null,
        needs_confirm: false,
        qr_svg: "",
        otpauth: "otpauth://totp/batonAI:baton-demo?secret=DEMO",
        code: null,
        code_expires_in: 30,
        virtual: true,
      };
    },
    async virtual_pair() {
      return {
        ok: true,
        status: "needs_confirm",
        pair_id: "demo-pair",
        sas: "4821",
        pc_name: "DESKTOP-DEMO",
      };
    },
    async virtual_confirm() {
      return {
        ok: true,
        status: "paired",
        sas: "4821",
        pc_name: "DESKTOP-DEMO",
      };
    },
    async virtual_unpair() {
      return { ok: true, status: "unpaired" };
    },
    async virtual_reset() {
      return { ok: true, device_id: "baton-demo", short: "DEMO", qr_svg: "" };
    },
    async devices() {
      return {
        ok: true,
        devices: [
          {
            device_id: "baton-web-demo",
            name: "Panel web (dev)",
            last_seen_at: new Date().toISOString(),
            connected: true,
            revoked: 0,
          },
          {
            device_id: "baton-a1b2c3",
            name: "Mando de banco",
            last_seen_at: new Date(Date.now() - 3600_000).toISOString(),
            connected: false,
            revoked: 0,
          },
        ],
      };
    },
    async revoke_device() {
      return { ok: true, revoked: true };
    },
    async audit() {
      const now = new Date().toISOString();
      return {
        ok: true,
        approvals: [
          {
            approval_id: "apr_demo_1",
            agent_id: "opencode:ses_demo",
            title: "Ejecutar la suite de tests",
            command: "npm run test -- --coverage",
            status: "accepted",
            created_at: now,
            device_id: "baton-web-demo",
            source: "button",
          },
          {
            approval_id: "apr_demo_2",
            agent_id: "codex",
            title: "Limpiar artefactos",
            command: "rm -rf build/ dist/",
            status: "rejected",
            created_at: now,
            device_id: "baton-a1b2c3",
            source: "button",
          },
        ],
        events: [
          { ts: now, kind: "approval_resolved", agent_id: "opencode:ses_demo", device_id: "baton-web-demo" },
          { ts: now, kind: "device_paired", agent_id: null, device_id: "baton-web-demo" },
        ],
      };
    },
    async open_panel() {
      return { ok: true, url: "vista previa" };
    },
    async interrupt_agent() {
      return { ok: true };
    },
    async send_agent_text() {
      return { ok: true, chars: 1 };
    },
    async open_folder() {
      return { ok: true };
    },
  };
}

async function boot() {
  const api = await getApi();
  state.preview = !api;
  state.api = api || mockApi();
  $("refresh").addEventListener("click", refresh);
  $("open-panel").addEventListener("click", openPanel);
  $("virtual-pair").addEventListener("click", pairVirtual);
  $("virtual-unpair").addEventListener("click", unpairVirtual);
  $("virtual-reset").addEventListener("click", resetVirtual);
  $("virtual-show-code").addEventListener("change", renderVirtualCode);
  $("virtual-code").addEventListener("keydown", (event) => {
    if (event.key === "Enter") pairVirtual();
  });
  $("agent-search").addEventListener("input", (event) => {
    state.filters.query = event.target.value;
    render();
  });
  $("filter-status").addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    render();
  });
  $("filter-provider").addEventListener("change", (event) => {
    state.filters.provider = event.target.value;
    render();
  });
  $("filter-sort").addEventListener("change", (event) => {
    state.filters.sort = event.target.value;
    render();
  });
  $("show-all").addEventListener("click", showAllAgents);
  $("hide-all").addEventListener("click", hideAllAgents);
  $("clear-pins").addEventListener("click", clearAllPins);
  $("drawer-close").addEventListener("click", closeDrawer);
  $("drawer-backdrop").addEventListener("click", closeDrawer);
  $("connection-save").addEventListener("click", saveConnection);
  $("connection-local").addEventListener("click", useLocalConnection);
  $("remote-copy").addEventListener("click", copyRemoteConnection);
  $("discover-gateways").addEventListener("click", discoverGateways);
  $("pair-control").addEventListener("click", pairWithDevice);
  $("pair-code").addEventListener("keydown", (event) => {
    if (event.key === "Enter") pairWithDevice();
  });
  $("rest-save").addEventListener("click", saveRestConfig);
  $("rest-minutes").addEventListener("input", () => {
    state.restDirty = true;
  });
  for (const button of document.querySelectorAll("#limits-view button")) {
    button.addEventListener("click", () =>
      saveLimitsView(button.dataset.view)
    );
  }
  window.addEventListener("keydown", globalShortcuts);
  for (const tab of document.querySelectorAll(".tab[data-view]")) {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  }
  await loadConnection();
  await refresh();
  if (!state.preview) {
    // La detección vive en el gateway: refrescar en silencio hace que las
    // sesiones nuevas aparezcan sin que el usuario pulse «Recargar».
    setInterval(() => refresh({ silent: true }), REFRESH_MS);
  }
}

function setView(view) {
  if (!VIEWS[view]) return;
  state.view = view;
  closeDrawer();

  for (const tab of document.querySelectorAll(".tab[data-view]")) {
    const active = tab.dataset.view === view;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const section of document.querySelectorAll(".view[data-view]")) {
    section.hidden = section.dataset.view !== view;
  }

  $("view-title").textContent = VIEWS[view].title;
  $("view-lede").textContent = VIEWS[view].lede;
  hideBanner();
  refresh();
}

async function refresh(options = {}) {
  const silent = options.silent === true;
  const button = $("refresh");
  if (!silent) button.disabled = true;
  try {
    const status = await state.api.gateway_status();
    setGateway(status);
    state.gateway = status.gateway || state.gateway || "http://127.0.0.1:8770";

    if (!status.ok && !state.preview) {
      if (silent) return;
      showBanner(
        `No se pudo conectar con el gateway en ${status.gateway || "127.0.0.1:8770"}. ` +
        "Asegúrate de que está en marcha."
      );
      if (state.view === "agents") {
        state.agents = [];
        state.hidden = new Set();
        state.pinned = [];
        render();
      }
      return;
    }

    await loadView(status, silent);
  } catch (error) {
    if (silent) return;
    showBanner("Error inesperado al leer el gateway: " + String(error));
    if (state.view === "agents") {
      state.agents = [];
      state.hidden = new Set();
      state.pinned = [];
      render();
    }
  } finally {
    if (!silent) button.disabled = false;
  }
}

async function loadView(status, silent) {
  if (state.view === "agents") {
    const result = await state.api.list_agents();
    if (silent && (!result || !result.ok)) return;
    applyAgents(result);
    return;
  }
  if (state.view === "hardware") {
    await loadHardware(status, silent);
    return;
  }
  if (state.view === "audit") {
    await loadAudit(silent);
    return;
  }
  await loadSettings(status, silent);
}

function applyAgents(result) {
  if (!result || !result.ok) {
    state.agents = [];
    state.hidden = new Set();
    state.system = {};
    showBanner(
      `No se pudo cargar la lista de agentes. ¿Está el gateway en ${result && result.gateway ? result.gateway : "127.0.0.1:8770"}?`
    );
    render();
    return;
  }

  const incoming = Array.isArray(result.agents) ? result.agents : [];
  const previous = state.lastStatuses;

  state.agents = incoming;
  state.system = result.system || {};
  state.hidden = new Set(Array.isArray(result.hidden) ? result.hidden : []);
  state.pinned = Array.isArray(result.pinned) ? result.pinned : [];
  state.lastStatuses = new Map(incoming.map((agent) => [agent.id, agent.status]));

  notifyTransitions(previous, incoming);
  hideBanner();
  render();
}

function notifyTransitions(previous, agents) {
  if (!previous.size) return;
  for (const agent of agents) {
    if (state.hidden.has(agent.id)) continue;
    const old = previous.get(agent.id);
    if (!old || old === agent.status) continue;

    if (agent.status === "waiting_input") {
      showToast(`${agent.name} espera respuesta.`, "wait");
    } else if (
      agent.status === "done" &&
      (old === "running" || old === "waiting_input")
    ) {
      showToast(`${agent.name} ha terminado.`, "done");
    } else if (agent.status === "error") {
      showToast(`${agent.name} ha entrado en error.`, "error");
    }
  }
}

function showToast(text, kind = "info") {
  const box = $("toasts");
  if (!box) return;
  const toast = el("div", "toast", text);
  toast.dataset.kind = kind;
  box.append(toast);
  setTimeout(() => toast.remove(), 5200);
}

function setGateway(status) {
  const node = $("gateway");
  const text = $("gateway-text");

  if (state.preview) {
    node.dataset.state = "wait";
    text.textContent = "vista previa";
    node.title = "Datos de ejemplo (sin pywebview)";
    const connection = $("connection-state");
    if (connection) {
      connection.textContent = "vista previa";
      connection.dataset.state = "wait";
    }
    return;
  }

  if (status && status.ok) {
    node.dataset.state = "on";
    text.textContent = "gateway conectado";
    node.title = `${status.gateway} · v${status.version}`;
  } else {
    node.dataset.state = "off";
    text.textContent = "gateway sin conexión";
    node.title = (status && status.error) || "No se pudo conectar";
  }

  const connection = $("connection-state");
  if (connection) {
    if (status && status.ok) {
      const local = isLocalGatewayUrl(status.gateway || state.connection.url);
      connection.textContent = local ? "local" : "remoto";
      connection.dataset.state = local ? "on" : "wait";
    } else {
      connection.textContent = "sin conexión";
      connection.dataset.state = "off";
    }
  }
}

function isLocalGatewayUrl(url) {
  return !url || /127\.0\.0\.1|localhost/.test(String(url));
}

/* -- hardware ---------------------------------------------------------- */

function formatWhen(value) {
  if (!value) return "sin actividad";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "ahora";
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.floor(seconds / 3600)} h`;
  return date.toLocaleDateString();
}

async function loadHardware(status, silent = false) {
  const [devices, virtual] = await Promise.all([
    state.api.devices(),
    state.api.virtual_device(),
  ]);

  if (!devices || !devices.ok) {
    if (!silent) showBanner("No se pudo leer el estado del hardware.");
    return;
  }

  state.devices = Array.isArray(devices.devices) ? devices.devices : [];
  state.virtualDevice = virtual && virtual.ok ? virtual : null;
  state.hostname = (status && status.hostname) || state.hostname || "Este PC";

  $("panel-url").textContent = state.gateway || "http://127.0.0.1:8770";
  const connected = state.devices.filter((device) => device.connected).length;
  $("summary").textContent =
    `${state.devices.length} ${state.devices.length === 1 ? "dispositivo" : "dispositivos"} · ` +
    `${connected} ${connected === 1 ? "conectado" : "conectados"}`;
  $("devices-count").textContent = `${connected} en línea`;
  renderVirtual();
  renderDevices();
  hideBanner();
}

function renderVirtual() {
  const device = state.virtualDevice;
  const badge = $("virtual-state");
  const confirm = $("virtual-confirm");
  const result = $("virtual-result");

  if (!device) {
    $("virtual-id").textContent = "—";
    badge.textContent = "sin conexión";
    badge.dataset.state = "off";
    confirm.hidden = true;
    result.hidden = true;
    return;
  }

  $("virtual-id").textContent = device.device_id;

  if (device.paired) {
    badge.textContent = `emparejado con ${device.paired_to || "PC"}`;
    badge.dataset.state = "on";
  } else if (device.needs_confirm) {
    badge.textContent = "esperando A en el dispositivo";
    badge.dataset.state = "wait";
  } else {
    badge.textContent = "sin emparejar";
    badge.dataset.state = "wait";
  }

  confirm.hidden = !device.needs_confirm;
  if (device.needs_confirm) {
    $("virtual-sas").textContent = device.sas || "----";
  }

  if (device.paired) {
    result.hidden = false;
    result.dataset.state = "on";
    result.textContent = `Emparejado con ${device.paired_to || "este PC"}.`;
  } else {
    result.hidden = true;
    result.textContent = "";
  }

  $("virtual-unpair").disabled = !device.paired;
  renderVirtualCode();
}

function startVirtualPoll() {
  if (state.virtualPoll) return;
  state.virtualPoll = setInterval(async () => {
    const device = await state.api.virtual_device();
    if (!device || !device.ok) return;
    state.virtualDevice = device;
    renderVirtual();
    if (device.paired) {
      stopVirtualPoll();
      state.virtualPairId = null;
      $("virtual-code").value = "";
      await refresh({ silent: true });
    }
  }, 1000);
}

function stopVirtualPoll() {
  if (!state.virtualPoll) return;
  clearInterval(state.virtualPoll);
  state.virtualPoll = null;
}

function renderVirtualCode() {
  const box = $("virtual-code-hint");
  const device = state.virtualDevice;
  const show = $("virtual-show-code").checked && device && device.code;
  if (!show) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.hidden = false;
  box.textContent =
    `Código actual (caduca en ${device.code_expires_in ?? "?"} s): ${device.code}`;
}

function virtualError(code) {
  const messages = {
    bad_code: "Código incorrecto. Espera al siguiente código del Authenticator.",
    rate_limited: "Demasiados intentos. Espera un minuto antes de reintentar.",
    replay: "Ese código ya se ha usado. Espera al siguiente.",
    expired: "La confirmación caducó. Vuelve a introducir el código.",
    unknown_pair: "No hay un emparejamiento pendiente.",
    agent_not_found: "El dispositivo virtual no está disponible.",
  };
  return messages[code] || `No se pudo emparejar (${code || "error"}).`;
}

async function pairVirtual() {
  const input = $("virtual-code");
  const code = input.value.replace(/\D/g, "").slice(0, 6);
  if (code.length !== 6) {
    showBanner("Escribe los 6 dígitos que muestra Google Authenticator.");
    return;
  }

  const button = $("virtual-pair");
  button.disabled = true;
  try {
    const result = await state.api.virtual_pair(
      code,
      state.hostname || "Este PC"
    );
    if (!result || !result.ok) {
      showBanner(virtualError(result && result.error));
      return;
    }

    if (result.status === "needs_confirm") {
      state.virtualPairId = result.pair_id;
      $("virtual-sas").textContent = result.sas || "----";
      $("virtual-confirm").hidden = false;
      $("virtual-result").hidden = true;
      hideBanner();
      startVirtualPoll();
      return;
    }

    state.virtualPairId = null;
    stopVirtualPoll();
    input.value = "";
    hideBanner();
    await refresh();
  } catch (error) {
    showBanner("Error al emparejar: " + String(error));
  } finally {
    button.disabled = false;
  }
}

async function unpairVirtual() {
  if (!window.confirm("¿Desemparejar el dispositivo virtual de este PC?")) return;
  try {
    const result = await state.api.virtual_unpair();
    if (!result || !result.ok) {
      showBanner(virtualError(result && result.error));
      return;
    }
    state.virtualPairId = null;
    stopVirtualPoll();
    hideBanner();
    await refresh();
  } catch (error) {
    showBanner("Error al desemparejar: " + String(error));
  }
}

async function resetVirtual() {
  if (
    !window.confirm(
      "Se generará un dispositivo y un QR nuevos. Habrá que volver a escanearlo. ¿Continuar?"
    )
  ) {
    return;
  }
  try {
    const result = await state.api.virtual_reset();
    if (!result || !result.ok) {
      showBanner(virtualError(result && result.error));
      return;
    }
    state.virtualPairId = null;
    stopVirtualPoll();
    $("virtual-code").value = "";
    hideBanner();
    await refresh();
  } catch (error) {
    showBanner("Error al generar el QR: " + String(error));
  }
}

function renderDevices() {
  const box = $("devices");
  box.replaceChildren();

  if (!state.devices.length) {
    box.append(el("p", "empty", "No hay dispositivos emparejados todavía."));
    return;
  }

  for (const device of state.devices) {
    const revoked = Boolean(device.revoked);
    const connected = Boolean(device.connected) && !revoked;
    const row = el("article", "device");

    const identity = el("div", "device-id");
    identity.append(
      el("div", "device-name", device.name || device.device_id),
      el("div", "device-key mono", device.device_id)
    );

    const badge = el(
      "span",
      "badge",
      revoked ? "revocado" : connected ? "conectado" : "desconectado"
    );
    badge.dataset.state = revoked ? "off" : connected ? "on" : "wait";

    const meta = el("div", "device-meta");
    meta.append(badge, el("span", "muted", formatWhen(device.last_seen_at)));

    row.append(identity, meta);

    if (!revoked) {
      const revoke = el("button", "mini danger", "Revocar");
      revoke.type = "button";
      revoke.addEventListener("click", () => revokeDevice(device));
      row.append(revoke);
    }

    box.append(row);
  }
}

async function revokeDevice(device) {
  const name = device.name || device.device_id;
  if (!window.confirm(`¿Revocar el acceso de ${name}?`)) return;
  try {
    const result = await state.api.revoke_device(device.device_id);
    if (!result || !result.ok || !result.revoked) {
      showBanner("No se pudo revocar el dispositivo.");
      return;
    }
    await refresh();
  } catch (error) {
    showBanner("Error al revocar el dispositivo: " + String(error));
  }
}

async function openPanel() {
  try {
    const result = await state.api.open_panel();
    if (!result || !result.ok) {
      showBanner("No se pudo abrir el panel en el navegador.");
    }
  } catch (error) {
    showBanner("Error al abrir el panel: " + String(error));
  }
}

/* -- auditoría --------------------------------------------------------- */

async function loadAudit(silent = false) {
  const result = await state.api.audit(40);
  if (!result || !result.ok) {
    if (!silent) showBanner("No se pudo leer la auditoría.");
    return;
  }

  state.audit = {
    approvals: Array.isArray(result.approvals) ? result.approvals : [],
    events: Array.isArray(result.events) ? result.events : [],
  };

  $("summary").textContent =
    `${state.audit.approvals.length} aprobaciones · ` +
    `${state.audit.events.length} eventos`;
  $("audit-count").textContent = `${state.audit.approvals.length} registradas`;
  renderAudit();
  hideBanner();
}

function auditBadge(status) {
  const labels = {
    accepted: ["permitida", "on"],
    rejected: ["denegada", "off"],
    expired: ["caducada", "wait"],
    stale: ["obsoleta", "muted"],
    pending: ["pendiente", "wait"],
  };
  const [label, stateName] = labels[status] || [status || "desconocida", "muted"];
  const badge = el("span", "badge", label);
  badge.dataset.state = stateName;
  return badge;
}

function renderAudit() {
  const approvals = $("approvals");
  approvals.replaceChildren();
  if (!state.audit.approvals.length) {
    approvals.append(el("p", "empty", "Sin aprobaciones registradas."));
  } else {
    for (const approval of state.audit.approvals) {
      const row = el("article", "audit-row");
      const top = el("div", "audit-top");
      top.append(
        el("span", "audit-time", formatWhen(approval.created_at)),
        auditBadge(approval.status)
      );
      if (approval.risk) {
        const risk = el(
          "span",
          "risk",
          RISK_LABELS[approval.risk] || approval.risk
        );
        risk.dataset.risk = approval.risk;
        top.append(risk);
      }
      top.append(el("span", "audit-agent mono", approval.agent_id || "—"));

      const title = el("div", "audit-title", approval.title || approval.approval_id);
      const command = el(
        "div",
        "audit-command mono",
        approval.command || "—"
      );
      command.title = approval.command || "";

      const meta = el(
        "div",
        "audit-meta muted",
        [
          approval.device_id,
          approval.source,
          approval.resolved_at ? `resuelta ${formatWhen(approval.resolved_at)}` : "",
        ]
          .filter(Boolean)
          .join(" · ")
      );

      row.append(top, title, command, meta);
      const details = Array.isArray(approval.risk_details)
        ? approval.risk_details
        : [];
      if (details.length) {
        row.append(el("div", "audit-meta muted", details.join(" · ")));
      }
      approvals.append(row);
    }
  }

  const events = $("events");
  events.replaceChildren();
  if (!state.audit.events.length) {
    events.append(el("p", "empty", "Sin eventos registrados."));
  } else {
    for (const event of state.audit.events) {
      const row = el("div", "event-row");
      row.append(
        el("span", "audit-time", formatWhen(event.ts)),
        el("span", "event-kind mono", event.kind || "evento"),
        el(
          "span",
          "muted",
          [event.agent_id, event.device_id].filter(Boolean).join(" · ")
        )
      );
      events.append(row);
    }
  }
}

/* -- ajustes ----------------------------------------------------------- */

async function loadConnection() {
  if (!state.api) return;
  const config = await state.api.connection_config();
  if (config && config.ok) {
    state.connection.url = config.gateway_url || "";
    state.connection.token = config.token || "";
    $("connection-url").value = state.connection.url;
    $("connection-token").value = state.connection.token;
  }
  const remote = state.api.remote_config
    ? await state.api.remote_config()
    : null;
  state.connection.remote = remote;
  renderConnection();
}

function renderConnection() {
  const remote = state.connection.remote;
  const box = $("remote-access");
  const note = $("connection-note");
  if (!box) return;

  const show = Boolean(remote && remote.ok && remote.lan && remote.token);
  box.hidden = !show;
  if (show) {
    const urls = Array.isArray(remote.urls) ? remote.urls : [];
    $("remote-url").textContent =
      remote.url || (urls[0] && urls[0].url) || "—";
    $("remote-token").textContent = remote.token;
    const alternatives = urls.filter((item) => item.url !== remote.url);
    $("remote-alt").textContent = alternatives.length
      ? "Otras interfaces: " +
        alternatives
          .map((item) => `${item.interface}: ${item.url}`)
          .join(" · ")
      : "";
  }

  if (note && remote && remote.ok && !remote.lan) {
    note.textContent =
      "Este gateway escucha solo en local. Para acceso remoto, arráncalo con BATON_HOST=0.0.0.0.";
    note.dataset.state = "error";
  } else if (note && (!remote || !remote.ok)) {
    note.textContent = "";
    note.dataset.state = "";
  }
}

const PAIR_ERRORS = {
  bad_code: "Código incorrecto.",
  rate_limited: "Demasiados intentos. Espera un minuto.",
  replay: "Ese código ya se usó. Espera al siguiente.",
  expired: "El código ha caducado. Prueba con el siguiente.",
  virtual_device_disabled: "El dispositivo virtual está desactivado.",
  pair_failed: "No se pudo vincular el dispositivo.",
};

function pairError(error) {
  return PAIR_ERRORS[error] || "No se pudo vincular: " + String(error);
}

function selectPairingGateway(gateway) {
  state.pairingGateway = gateway;
  for (const item of document.querySelectorAll(".gateway-item")) {
    item.classList.toggle(
      "is-selected",
      item.dataset.url === gateway.url
    );
  }
  const row = $("pair-row");
  row.hidden = false;
  const note = $("discover-note");
  note.textContent = `Dispositivo: ${
    gateway.hostname || gateway.url
  }. Escribe el código de Google Authenticator.`;
  note.dataset.state = "ok";
  $("pair-code").focus();
}

async function discoverGateways() {
  const button = $("discover-gateways");
  const note = $("discover-note");
  const list = $("gateway-list");
  button.disabled = true;
  note.textContent = "Buscando dispositivos en la red…";
  note.dataset.state = "";
  list.replaceChildren();
  $("pair-row").hidden = true;
  state.pairingGateway = null;
  try {
    const result = await state.api.discover_gateways();
    if (!result || !result.ok) {
      note.textContent = "No se pudo buscar dispositivos.";
      note.dataset.state = "error";
      return;
    }
    const gateways = Array.isArray(result.gateways)
      ? result.gateways
      : [];
    state.discoveredGateways = gateways;
    if (!gateways.length) {
      note.textContent =
        "No se encontró ningún dispositivo. Comprueba que estén en la misma red.";
      note.dataset.state = "error";
      return;
    }
    note.textContent =
      "Dispositivos encontrados. Elige el del QR que has escaneado.";
    note.dataset.state = "ok";
    for (const gateway of gateways) {
      const item = el("button", "gateway-item");
      item.type = "button";
      item.dataset.url = gateway.url;
      const name = el(
        "span",
        "gateway-name",
        `${gateway.hostname || "batonAI"}${gateway.local ? " · este PC" : ""}`
      );
      const url = el("span", "gateway-url", gateway.url);
      item.append(name, url);
      item.addEventListener("click", () => selectPairingGateway(gateway));
      list.append(item);
    }
    const remote = gateways.filter((gateway) => !gateway.local);
    if (remote.length === 1) selectPairingGateway(remote[0]);
  } catch (error) {
    note.textContent = "Error al buscar: " + String(error);
    note.dataset.state = "error";
  } finally {
    button.disabled = false;
  }
}

async function pairWithDevice() {
  const gateway = state.pairingGateway;
  const note = $("discover-note");
  const code = $("pair-code").value.trim();
  if (!gateway) {
    note.textContent = "Primero elige un dispositivo.";
    note.dataset.state = "error";
    return;
  }
  if (!/^\d{6}$/.test(code)) {
    note.textContent = "Escribe los 6 dígitos de Google Authenticator.";
    note.dataset.state = "error";
    return;
  }
  const button = $("pair-control");
  button.disabled = true;
  try {
    const result = await state.api.pair_control(gateway.url, code);
    if (!result || !result.ok) {
      note.textContent = pairError(result && result.error);
      note.dataset.state = "error";
      return;
    }
    note.textContent = "Vinculado. Conectando…";
    note.dataset.state = "ok";
    $("pair-row").hidden = true;
    $("pair-code").value = "";
    await loadConnection();
    await refresh();
    note.textContent = "Vinculado correctamente.";
    note.dataset.state = "ok";
  } catch (error) {
    note.textContent = "Error al vincular: " + String(error);
    note.dataset.state = "error";
  } finally {
    button.disabled = false;
  }
}

async function saveConnection() {
  const note = $("connection-note");
  const url = $("connection-url").value.trim();
  const token = $("connection-token").value.trim();
  try {
    const result = await state.api.set_connection_config(url, token);
    if (!result || !result.ok) {
      note.textContent = "No se pudo guardar la conexión.";
      note.dataset.state = "error";
      return;
    }
    state.connection.url = result.gateway_url;
    state.connection.token = result.token;
    $("connection-url").value = result.gateway_url;
    $("connection-token").value = result.token;
    note.textContent = "Conexión guardada. Reconectando…";
    note.dataset.state = "ok";
    await refresh();
    await loadConnection();
    note.textContent = "Conexión guardada.";
    note.dataset.state = "ok";
  } catch (error) {
    note.textContent = "Error al guardar: " + String(error);
    note.dataset.state = "error";
  }
}

async function useLocalConnection() {
  $("connection-url").value = "http://127.0.0.1:8770";
  $("connection-token").value = "";
  await saveConnection();
}

async function copyRemoteConnection() {
  const remote = state.connection.remote;
  if (!remote || !remote.ok) return;
  const text = `Gateway: ${remote.url || ""}\nToken: ${remote.token || ""}`;
  try {
    await navigator.clipboard.writeText(text);
    const note = $("connection-note");
    note.textContent = "URL y token copiados.";
    note.dataset.state = "ok";
  } catch (error) {
    const note = $("connection-note");
    note.textContent = "No se pudo copiar: " + String(error);
    note.dataset.state = "error";
  }
}

async function loadSettings(status, silent = false) {
  const [info, limits] = await Promise.all([
    state.api.gateway_info(),
    state.api.limits
      ? state.api.limits()
      : Promise.resolve(null),
  ]);
  if (!info || !info.ok) {
    if (!silent) showBanner("No se pudo leer la configuración del gateway.");
    return;
  }

  state.info = info;
  state.limits = limits && limits.ok !== undefined
    ? {
        ok: Boolean(limits.ok),
        providers: Array.isArray(limits.providers) ? limits.providers : [],
        period: limits.period || "all",
        view: limits.view || info.limits_view || "remaining",
        selected_windows: Array.isArray(limits.selected_windows)
          ? limits.selected_windows
          : null,
        error: limits.error || null,
        read_at: limits.read_at || null,
      }
    : {
        ok: false,
        providers: [],
        period: "all",
        view: info.limits_view || "remaining",
        selected_windows: null,
        error: "unavailable",
        read_at: null,
      };
  state.limitsView = state.limits.view;

  const minutes = Math.max(0, Math.round((Number(info.rest_after_s) || 0) / 60));
  const input = $("rest-minutes");
  if (!state.restDirty && document.activeElement !== input) {
    input.value = String(minutes);
  }
  $("summary").textContent = `gateway v${info.version || "?"}`;
  renderSettings();
  renderLimits();
  hideBanner();
}

async function saveRestConfig() {
  const input = $("rest-minutes");
  const minutes = Number(input.value);
  const note = $("rest-save-note");
  if (!Number.isFinite(minutes) || minutes < 0 || minutes > 60) {
    note.textContent = "Escribe un número entre 0 y 60 minutos.";
    note.dataset.state = "error";
    return;
  }

  const button = $("rest-save");
  button.disabled = true;
  try {
    const result = await state.api.set_rest_config(Math.round(minutes * 60));
    if (!result || !result.ok) {
      note.textContent = "No se pudo guardar el modo reposo.";
      note.dataset.state = "error";
      return;
    }
    const saved = Math.round((Number(result.rest_after_s) || 0) / 60);
    input.value = String(saved);
    state.restDirty = false;
    note.textContent =
      saved === 0
        ? "Modo reposo desactivado."
        : `Guardado: ${saved} min. El panel lo aplica en menos de 30 s.`;
    note.dataset.state = "ok";
    if (state.info) state.info.rest_after_s = result.rest_after_s;
  } catch (error) {
    note.textContent = "Error al guardar: " + String(error);
    note.dataset.state = "error";
  } finally {
    button.disabled = false;
  }
}

async function saveLimitsView(view) {
  const note = $("limits-note");
  try {
    const result = await state.api.set_limits_view(view);
    if (!result || !result.ok) {
      note.textContent = "No se pudo guardar la vista de límites.";
      note.dataset.state = "error";
      return;
    }
    state.limitsView = result.limits_view || view;
    state.limits.view = state.limitsView;
    renderLimits();
    note.textContent = "Guardado. El dispositivo se actualiza en el próximo minuto.";
    note.dataset.state = "ok";
  } catch (error) {
    note.textContent = "Error al guardar: " + String(error);
    note.dataset.state = "error";
  }
}

function formatReset(resetsAt) {
  if (!resetsAt) return "";
  const seconds = Number(resetsAt) - Date.now() / 1000;
  if (!Number.isFinite(seconds)) return "";
  if (seconds <= 0) return "ahora";
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) {
    return `${hours} h${restMinutes ? ` ${restMinutes} min` : ""}`;
  }
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return `${days} d${restHours ? ` ${restHours} h` : ""}`;
}

const LIMIT_ERROR_LABELS = {
  not_installed: "no instalado",
  not_running: "no está arrancado",
  not_signed_in: "sin sesión",
  not_authenticated: "sin sesión",
  token_expired: "sesión caducada",
  auth_failed: "sesión caducada",
  unreachable: "sin conexión",
  invalid_response: "respuesta no válida",
  http_error: "error del servicio",
  disabled: "desactivado",
  no_sources: "sin datos",
};

function limitProviderError(provider) {
  return LIMIT_ERROR_LABELS[provider.error] || "sin datos";
}

function limitPlanLabel(plan) {
  return plan ? String(plan).toUpperCase() : "conectado";
}

function limitLevel(remaining) {
  if (remaining <= 20) return "low";
  if (remaining <= 50) return "warn";
  return "ok";
}

function formatResetLabel(resetsAt) {
  const text = formatReset(resetsAt);
  return text ? `↻ ${text}` : "sin renovación";
}

function windowKey(provider, window) {
  return window.key || `${provider.id}:${window.id}`;
}

function allLimitWindows(providers) {
  const entries = [];
  for (const provider of providers) {
    for (const window of provider.windows || []) {
      entries.push({
        provider,
        window,
        key: windowKey(provider, window),
      });
    }
  }
  return entries;
}

function selectedLimitWindows(data, installed) {
  if (
    data.selected_windows === null ||
    data.selected_windows === undefined
  ) {
    return new Set(allLimitWindows(installed).map((entry) => entry.key));
  }
  return new Set(data.selected_windows);
}

function limitWindowCard(provider, window, selected, view) {
  const used = Math.max(0, Math.min(100, Number(window.used_percent) || 0));
  const remaining = Number.isFinite(Number(window.remaining_percent))
    ? Math.max(0, Math.min(100, Number(window.remaining_percent)))
    : 100 - used;
  const level = limitLevel(remaining);
  const usedMode = view === "used";
  const value = usedMode ? used : remaining;

  const card = el("article", "limit-window");
  card.dataset.level = level;
  card.dataset.selected = selected ? "true" : "false";

  const head = el("div", "limit-window-head");
  head.append(
    el("span", "limit-window-name", window.label || window.id)
  );
  const eye = el("button", "limit-eye", "");
  eye.type = "button";
  eye.innerHTML = eyeIcon(selected);
  eye.title = selected
    ? "Ocultar esta ventana del dispositivo"
    : "Mostrar esta ventana en el dispositivo";
  eye.setAttribute("aria-pressed", String(selected));
  eye.setAttribute("aria-label", eye.title);
  eye.addEventListener("click", () =>
    toggleLimitWindow(windowKey(provider, window), !selected)
  );
  head.append(eye);
  card.append(head);

  const valueNode = el("div", "limit-window-value");
  valueNode.append(
    el("strong", "", `${value}%`),
    el("span", "", usedMode ? "usado" : "disponible")
  );

  const bar = el("div", "limit-bar");
  const fill = el("span", "limit-bar-fill");
  fill.style.width = `${value}%`;
  bar.append(fill);

  const foot = el("div", "limit-window-foot");
  foot.append(
    el(
      "span",
      "",
      usedMode ? `${remaining}% disponible` : `${used}% usado`
    ),
    el("span", "reset", formatResetLabel(window.resets_at))
  );

  card.append(valueNode, bar, foot);
  return card;
}

function budgetCard(budget, view) {
  const used = Math.max(0, Math.min(100, Number(budget.used_percent) || 0));
  const remaining = Number.isFinite(Number(budget.remaining_percent))
    ? Math.max(0, Math.min(100, Number(budget.remaining_percent)))
    : 100 - used;
  const level = limitLevel(remaining);
  const usedMode = view === "used";
  const value = usedMode ? used : remaining;

  const card = el("article", "limit-window");
  card.dataset.level = level;
  card.append(
    el("span", "limit-window-name", budget.label || "Presupuesto")
  );
  const valueNode = el("div", "limit-window-value");
  valueNode.append(
    el("strong", "", `${value}%`),
    el("span", "", usedMode ? "usado" : "disponible")
  );
  const bar = el("div", "limit-bar");
  const fill = el("span", "limit-bar-fill");
  fill.style.width = `${value}%`;
  bar.append(fill);
  const foot = el("div", "limit-window-foot");
  foot.append(
    el(
      "span",
      "",
      `$${Number(budget.spent_usd || 0).toFixed(2)} de $${Number(
        budget.limit_usd || 0
      ).toFixed(2)}`
    ),
    el("span", "reset", formatResetLabel(budget.resets_at))
  );
  card.append(valueNode, bar, foot);
  return card;
}

function summaryStat(value, label, level = "ok") {
  const stat = el("div", "limit-summary-stat");
  stat.dataset.level = level;
  stat.append(el("b", "", String(value)), el("span", "", label));
  return stat;
}

function renderLimitSummary(installed, entries, selectedKeys) {
  const box = $("limits-summary");
  if (!box) return;
  const selectedEntries = entries.filter((entry) =>
    selectedKeys.has(entry.key)
  );
  const low = selectedEntries.filter(
    (entry) => Number(entry.window.remaining_percent) <= 20
  ).length;
  box.replaceChildren(
    summaryStat(installed.length, installed.length === 1 ? "IA" : "IAs"),
    summaryStat(
      selectedEntries.length,
      "En dispositivo"
    ),
    summaryStat(low, "En aviso", low ? "low" : "ok")
  );
}

function renderTickerPreview(installed, selectedKeys) {
  const node = $("ticker-preview");
  if (!node) return;
  const selectedEntries = allLimitWindows(installed).filter((entry) =>
    selectedKeys.has(entry.key)
  );
  if (!selectedEntries.length) {
    node.textContent = "Ninguna ventana seleccionada";
    node.dataset.state = "error";
    return;
  }
  const names = [...new Set(
    selectedEntries.map((entry) => entry.provider.label)
  )];
  node.textContent = `${selectedEntries.length} ${
    selectedEntries.length === 1 ? "ventana" : "ventanas"
  } · ${names.join(" + ")} · ${
    state.limitsView === "used" ? "gastado" : "restante"
  }`;
  node.dataset.state = "ok";
}

function renderLimitsViewControl() {
  for (const button of document.querySelectorAll("#limits-view button")) {
    const active = button.dataset.view === state.limitsView;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}

function providerHint(provider) {
  if (provider.error === "not_running") {
    return "Abre la aplicación para leer sus límites.";
  }
  if (
    provider.error === "not_authenticated" ||
    provider.error === "not_signed_in" ||
    provider.error === "token_expired" ||
    provider.error === "auth_failed"
  ) {
    return "Inicia sesión en esa IA para leer sus límites.";
  }
  if (provider.error === "unreachable") {
    return "No se pudo conectar con el servicio local.";
  }
  return "Comprueba que la IA esté instalada y arrancada.";
}

function renderLimits() {
  const data = state.limits || {};
  const box = $("limits-providers");
  const note = $("limits-status");
  if (!box) return;

  const installed = (data.providers || []).filter(
    (provider) => provider.installed
  );
  const entries = allLimitWindows(installed);
  const selected = selectedLimitWindows(data, installed);
  const withData = installed.filter((provider) => provider.ok);
  const view = state.limitsView;

  renderLimitSummary(installed, entries, selected);
  renderTickerPreview(installed, selected);
  renderLimitsViewControl();

  if (note) {
    if (data.error === "disabled") {
      note.textContent = "La lectura de límites está desactivada.";
      note.dataset.state = "error";
    } else if (!installed.length) {
      note.textContent =
        "No se detectaron IAs con límites. Abre OpenCode, Codex o Claude Code.";
      note.dataset.state = "error";
    } else {
      note.textContent = `${withData.length} con datos${
        data.read_at ? ` · actualizado ${formatWhen(data.read_at)}` : ""
      }`;
      note.dataset.state = withData.length ? "ok" : "error";
    }
  }

  box.replaceChildren();

  if (!installed.length) {
    box.append(
      el(
        "p",
        "empty",
        "Abre OpenCode, Codex o Claude Code y vuelve a cargar esta pantalla."
      )
    );
    return;
  }

  for (const provider of installed) {
    const section = el("section", "limit-provider");
    section.dataset.provider = provider.id;

    const head = el("header", "limit-provider-head");
    const identity = el("div", "limit-provider-id");
    identity.append(el("span", "provider-dot"));
    const copy = el("div", "limit-provider-copy");
    copy.append(el("span", "limit-provider-name", provider.label));
    const meta = provider.ok
      ? [
          provider.plan
            ? `Plan ${limitPlanLabel(provider.plan)}`
            : "conectado",
        ]
      : [limitProviderError(provider)];
    if (provider.workspace) meta.push(provider.workspace);
    copy.append(el("span", "limit-provider-meta", meta.join(" · ")));
    identity.append(copy);

    const providerEntries = entries.filter(
      (entry) => entry.provider.id === provider.id
    );
    const visibleCount = providerEntries.filter((entry) =>
      selected.has(entry.key)
    ).length;
    head.append(
      identity,
      el(
        "span",
        "limit-provider-count",
        provider.ok
          ? `${visibleCount}/${providerEntries.length} en dispositivo`
          : "sin datos"
      )
    );
    section.append(head);

    if (!provider.ok) {
      section.append(el("p", "limit-provider-error", providerHint(provider)));
      box.append(section);
      continue;
    }

    if (providerEntries.length) {
      const grid = el("div", "limit-window-grid");
      for (const entry of providerEntries) {
        grid.append(
          limitWindowCard(
            provider,
            entry.window,
            selected.has(entry.key),
            view
          )
        );
      }
      section.append(grid);
    } else {
      section.append(
        el("p", "limit-provider-error", "No devuelve ventanas de límite.")
      );
    }

    const budgets = Array.isArray(provider.budgets)
      ? provider.budgets
      : [];
    if (budgets.length) {
      section.append(el("div", "limit-budget-kicker", "Presupuestos"));
      const grid = el("div", "limit-window-grid");
      for (const budget of budgets) grid.append(budgetCard(budget, view));
      section.append(grid);
    }

    box.append(section);
  }
}

async function toggleLimitWindow(key, visible) {
  const note = $("limits-note");
  const installed = (state.limits.providers || []).filter(
    (provider) => provider.installed
  );
  const entries = allLimitWindows(installed);
  const selected = selectedLimitWindows(state.limits, installed);
  if (visible) selected.add(key);
  else selected.delete(key);
  const keys = entries
    .map((entry) => entry.key)
    .filter((item) => selected.has(item));
  const payload = keys.length === entries.length ? null : keys;

  for (const provider of state.limits.providers || []) {
    for (const window of provider.windows || []) {
      if (windowKey(provider, window) === key) {
        window.selected = visible;
      }
    }
  }

  try {
    const result = await state.api.set_limit_windows(payload);
    if (!result || !result.ok) {
      note.textContent = "No se pudo cambiar la ventana del dispositivo.";
      note.dataset.state = "error";
      renderLimits();
      return;
    }
    state.limits.selected_windows =
      result.selected_windows ?? payload;
    renderLimits();
    note.textContent = visible
      ? "Ventana activada en el dispositivo."
      : "Ventana ocultada del dispositivo.";
    note.dataset.state = "ok";
  } catch (error) {
    note.textContent = "Error al guardar: " + String(error);
    note.dataset.state = "error";
  }
}

function settingRow(label, value) {
  const row = el("div", "setting-row");
  row.append(
    el("span", "setting-label", label),
    el("span", "setting-value", String(value))
  );
  return row;
}

function settingCard(title, rows) {
  const card = el("article", "card settings-card");
  card.append(el("span", "card-kicker", title));
  for (const row of rows) card.append(row);
  return card;
}

function aboutCard() {
  const card = el("article", "card settings-card about-card");
  const mark = el("img", "about-mark");
  mark.src = "logo-glyph.svg";
  mark.alt = "";
  mark.width = 44;
  mark.height = 44;

  const copy = el("div", "about-copy");
  const name = el("div", "about-name");
  name.append("baton", el("span", "about-ai", "AI"));
  copy.append(name, el("p", "about-line", "Centro de control de agentes"));

  card.append(mark, copy);
  return card;
}

function yesNo(value) {
  return value ? "sí" : "no";
}

function formatSeconds(value) {
  const seconds = Number(value) || 0;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(seconds % 3600 ? 1 : 0)} h`;
}

function renderSettings() {
  const info = state.info;
  const box = $("settings");
  box.replaceChildren();
  if (!info) {
    box.append(el("p", "empty", "Sin datos del gateway."));
    return;
  }

  const gatewayCard = settingCard("Gateway", [
    settingRow("URL", info.gateway || state.gateway),
    settingRow("Versión", info.version || "—"),
    settingRow("Agentes", info.agents ?? "—"),
    settingRow("Dispositivos", info.connected_devices ?? "—"),
    settingRow("Modo desarrollo", yesNo(info.dev_mode)),
  ]);
  box.append(gatewayCard);

  const detectionRows = [
    settingRow("OpenCode", yesNo(info.opencode_enabled)),
    settingRow("Agentes locales", yesNo(info.local_agents_enabled)),
    settingRow("Falsos (demo)", yesNo(info.fake_autostart)),
  ];
  const sources = Array.isArray(info.sources) ? info.sources : [];
  if (sources.length) {
    const chips = el("div", "chips");
    for (const source of sources) {
      chips.append(el("span", "chip", source.label || source.id));
    }
    const row = el("div", "setting-row");
    row.append(el("span", "setting-label", "Fuentes"), chips);
    detectionRows.push(row);
  }
  box.append(settingCard("Detección", detectionRows));

  box.append(
    settingCard("Sesión y permisos", [
      settingRow("Fijados máximo", info.max_pinned ?? 2),
      settingRow("Caducidad de permiso", formatSeconds(info.approval_timeout_s)),
      settingRow("Heartbeat", formatSeconds(info.heartbeat_s)),
    ])
  );

  box.append(
    settingCard("Ritmo de descubrimiento", [
      settingRow(
        "OpenCode · ventana",
        formatSeconds(info.opencode_recency_s)
      ),
      settingRow("OpenCode · máximo", info.opencode_max_sessions ?? "—"),
      settingRow("OpenCode · sondeo", formatSeconds(info.opencode_poll_s)),
      settingRow(
        "Locales · ventana",
        formatSeconds(info.local_agents_recency_s)
      ),
      settingRow("Locales · máximo", info.local_agents_max_sessions ?? "—"),
      settingRow("Locales · sondeo", formatSeconds(info.local_agents_poll_s)),
      settingRow(
        "Locales · activo",
        formatSeconds(info.local_agents_active_s)
      ),
    ])
  );

  box.append(aboutCard());

  box.append(
    el(
      "p",
      "settings-note muted",
      "La configuración se cambia con variables BATON_* al arrancar el gateway."
    )
  );
}

function render() {
  const grid = $("agents");
  grid.replaceChildren();
  renderProviderOptions();
  renderStats();

  const total = state.agents.length;
  const hidden = state.agents.filter((agent) => state.hidden.has(agent.id)).length;
  const pinnedSet = new Set(state.pinned);
  const pinned = state.agents.filter((agent) => pinnedSet.has(agent.id)).length;
  const waiting = state.agents.filter((a) => a.status === "waiting_input").length;

  if (!total) {
    $("summary").textContent = "Sin agentes";
    grid.append(el("p", "empty", "No hay agentes registrados en el gateway."));
    return;
  }

  $("summary").textContent =
    `${total} ${total === 1 ? "agente" : "agentes"} · ` +
    `${waiting} esperando · ` +
    `${hidden} ${hidden === 1 ? "oculto" : "ocultos"} · ` +
    `${pinned} ${pinned === 1 ? "fijado" : "fijados"}`;

  const visible = filteredAgents();
  if (!visible.length) {
    grid.append(
      el("p", "empty", "Ningún agente coincide con los filtros.")
    );
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const agent of visible) fragment.append(agentCard(agent));
  grid.append(fragment);

  const editing =
    document.activeElement &&
    document.activeElement.id === "drawer-message";
  if (state.detailId && !editing) {
    renderDrawer();
  }
}

function providerLabel(provider) {
  const labels = {
    anthropic: "Anthropic",
    openai: "OpenAI",
    google: "Google",
    antigravity: "Antigravity",
    github: "GitHub",
    cursor: "Cursor",
    opencode: "OpenCode",
  };
  return labels[provider] || provider || "—";
}

function projectName(cwd) {
  if (!cwd) return "";
  const parts = cwd.split(/[\\/]+/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

function formatCost(value) {
  return `$${(Number(value) || 0).toFixed(4)}`;
}

function formatTokens(value) {
  return new Intl.NumberFormat("es").format(Number(value) || 0);
}

function statusMeta(status) {
  return STATUS_META[status] || { label: status || "—", tone: "muted", rank: 9 };
}

function filteredAgents() {
  const query = state.filters.query.trim().toLowerCase();
  const list = state.agents.filter((agent) => {
    if (state.filters.status !== "all" && agent.status !== state.filters.status) {
      return false;
    }
    if (
      state.filters.provider !== "all" &&
      agent.provider !== state.filters.provider
    ) {
      return false;
    }
    if (!query) return true;
    return [agent.name, agent.model, agent.provider, agent.cwd, agent.task]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });

  const pinnedSet = new Set(state.pinned);
  const sort = state.filters.sort;

  list.sort((left, right) => {
    const leftPinned = pinnedSet.has(left.id);
    const rightPinned = pinnedSet.has(right.id);
    if (leftPinned !== rightPinned) return leftPinned ? -1 : 1;
    if (leftPinned && rightPinned) {
      return state.pinned.indexOf(left.id) - state.pinned.indexOf(right.id);
    }
    if (sort === "name") return left.name.localeCompare(right.name, "es");
    if (sort === "recent") {
      return (
        new Date(right.last_event_at || 0) - new Date(left.last_event_at || 0)
      );
    }
    if (sort === "project") {
      return (
        projectName(left.cwd).localeCompare(projectName(right.cwd), "es") ||
        left.name.localeCompare(right.name, "es")
      );
    }
    return (
      statusMeta(left.status).rank - statusMeta(right.status).rank ||
      left.name.localeCompare(right.name, "es")
    );
  });

  return list;
}

function renderProviderOptions() {
  const select = $("filter-provider");
  const providers = [
    ...new Set(state.agents.map((agent) => agent.provider).filter(Boolean)),
  ].sort();
  const signature = providers.join("|");
  if (select.dataset.signature === signature) return;

  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "all";
  all.textContent = "Todos los proveedores";
  select.append(all);

  for (const provider of providers) {
    const option = document.createElement("option");
    option.value = provider;
    option.textContent = providerLabel(provider);
    select.append(option);
  }

  if (!providers.includes(state.filters.provider)) {
    state.filters.provider = "all";
  }
  select.value = state.filters.provider;
  select.dataset.signature = signature;
}

function renderStats() {
  const box = $("stats");
  box.replaceChildren();

  const counts = {
    waiting_input: 0,
    running: 0,
    done: 0,
    idle: 0,
    error: 0,
  };
  for (const agent of state.agents) {
    if (agent.status in counts) counts[agent.status] += 1;
  }

  const rows = [
    ["waiting_input", "esperando"],
    ["running", "trabajando"],
    ["done", "terminados"],
    ["idle", "en espera"],
    ["error", "error"],
  ];
  for (const [status, label] of rows) {
    const chip = el("span", "stat");
    chip.dataset.state = statusMeta(status).tone;
    chip.append(el("b", "", String(counts[status])), el("span", "", label));
    box.append(chip);
  }

  const system = state.system || {};
  const cost = el("span", "stat");
  cost.append(
    el("b", "", formatCost(system.total_cost)),
    el("span", "", "coste")
  );
  box.append(cost);

  const tokens = el("span", "stat");
  tokens.append(
    el("b", "", formatTokens(system.total_tokens)),
    el("span", "", "tokens")
  );
  box.append(tokens);
}

function agentCard(agent) {
  const isHidden = state.hidden.has(agent.id);
  const isPinned = state.pinned.includes(agent.id);
  const meta = statusMeta(agent.status);

  const channel = el("article", "channel");
  channel.tabIndex = 0;
  channel.setAttribute("role", "button");
  channel.setAttribute(
    "aria-label",
    `${agent.name}, ${meta.label}. Abrir detalle`
  );
  if (isHidden) channel.classList.add("is-hidden");
  if (isPinned) channel.classList.add("is-pinned");

  channel.append(logoNode(agent));

  const identity = el("div", "channel-id");
  const name = el("div", "channel-name");
  name.append(document.createTextNode(agent.name));
  if (isPinned) name.append(el("span", "channel-pin", "PIN"));
  identity.append(name);
  identity.append(
    el("div", "channel-model", `${agent.model} · ${providerLabel(agent.provider)}`)
  );

  const task = String(agent.task || "").replace(/\s+/g, " ").trim();
  const subtitle = [projectName(agent.cwd), task.slice(0, 140)]
    .filter(Boolean)
    .join(" · ");
  if (subtitle) identity.append(el("div", "channel-task", subtitle));
  channel.append(identity);

  const stateBox = el("div", "channel-state");
  const badge = el("span", "status-badge", meta.label);
  badge.dataset.state = meta.tone;
  stateBox.append(badge);

  const pin = el("button", "pin");
  pin.type = "button";
  pin.dataset.pinned = String(isPinned);
  pin.setAttribute("aria-pressed", String(isPinned));
  pin.setAttribute(
    "aria-label",
    isPinned ? `Desfijar ${agent.name}` : `Fijar ${agent.name} arriba`
  );
  pin.title = isPinned ? "Desfijar del hardware" : "Fijar arriba (máx. 2)";
  pin.innerHTML = pinIcon(isPinned);
  pin.addEventListener("click", (event) => {
    event.stopPropagation();
    togglePin(agent);
  });
  stateBox.append(pin);

  const eye = el("button", "eye");
  eye.type = "button";
  eye.dataset.visible = String(!isHidden);
  eye.setAttribute("aria-pressed", String(!isHidden));
  eye.setAttribute(
    "aria-label",
    !isHidden
      ? `Ocultar ${agent.name} del hardware`
      : `Mostrar ${agent.name} en el hardware`
  );
  eye.title = !isHidden ? "Ocultar del hardware" : "Mostrar en el hardware";
  eye.innerHTML = eyeIcon(!isHidden);
  eye.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleAgent(agent);
  });
  stateBox.append(eye);

  channel.append(stateBox);
  channel.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    openDrawer(agent.id);
  });
  channel.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openDrawer(agent.id);
    }
  });
  return channel;
}

/* -- detalle del agente ------------------------------------------------ */

function openDrawer(agentId) {
  state.detailId = agentId;
  state.drawerDraft = "";
  $("drawer").hidden = false;
  renderDrawer();
}

function closeDrawer() {
  state.detailId = null;
  state.drawerDraft = "";
  $("drawer").hidden = true;
}

function detailField(label, value, mono = false) {
  const field = el("div", "detail-field");
  field.append(
    el("div", "detail-label", label),
    el(
      "div",
      mono ? "detail-value mono" : "detail-value",
      value === undefined || value === null || value === "" ? "—" : String(value)
    )
  );
  return field;
}

function detailSection(title, ...children) {
  const section = el("section", "detail-section");
  section.append(el("div", "detail-kicker", title));
  for (const child of children) section.append(child);
  return section;
}

function renderDrawer() {
  const agent = state.agents.find((item) => item.id === state.detailId);
  if (!agent) {
    closeDrawer();
    return;
  }

  const meta = statusMeta(agent.status);
  const logo = $("drawer-logo");
  logo.innerHTML = logoSvg(agent);
  $("drawer-name").textContent = agent.name;
  $("drawer-sub").textContent = `${providerLabel(agent.provider)} · ${agent.model}`;

  const body = $("drawer-body");
  body.replaceChildren();

  const status = el("div", "detail-actions");
  const badge = el("span", "status-badge", meta.label);
  badge.dataset.state = meta.tone;
  status.append(
    badge,
    el("span", "muted", `desde ${formatWhen(agent.since)}`)
  );
  body.append(detailSection("Estado", status));

  const grid = el("div", "detail-grid");
  grid.append(
    detailField("Proyecto", projectName(agent.cwd)),
    detailField("Ruta", agent.cwd, true),
    detailField("Proveedor", providerLabel(agent.provider)),
    detailField("Modelo", agent.model, true),
    detailField("Último evento", formatWhen(agent.last_event_at)),
    detailField("Coste sesión", formatCost(agent.cost_session), true),
    detailField("Tokens", formatTokens(agent.tokens_session), true),
    detailField("ID", agent.id, true)
  );
  body.append(detailSection("Ficha", grid));

  if (agent.task) {
    body.append(detailSection("Tarea", el("div", "detail-value", agent.task)));
  }

  if (agent.approval_id) {
    const approval = el("div", "detail-value");
    approval.append(
      document.createTextNode(agent.prompt || "Permiso pendiente"),
      document.createTextNode(" ")
    );
    if (agent.risk) {
      const risk = el("span", "risk", RISK_LABELS[agent.risk] || agent.risk);
      risk.dataset.risk = agent.risk;
      approval.append(risk);
    }

    const details = Array.isArray(agent.risk_details)
      ? agent.risk_details
      : Array.isArray(agent.risk_reasons)
        ? agent.risk_reasons
        : [];
    const list = el("ul", "risk-details");
    if (details.length) {
      for (const detail of details) list.append(el("li", "", detail));
    } else {
      list.append(
        el("li", "", "No se reconoce como peligroso, pero puede modificar cosas.")
      );
    }

    body.append(
      detailSection(
        "Permiso pendiente",
        approval,
        list,
        el("p", "muted", "Resuélvelo en el dispositivo."),
        el("div", "muted", `id ${agent.approval_id}`)
      )
    );
  }

  const output = (agent.log_tail || []).join("\n").trim();
  body.append(
    detailSection(
      "Última salida",
      output
        ? el("pre", "detail-pre", output)
        : el("p", "muted", "Sin salida reciente.")
    )
  );

  const actions = el("div", "detail-actions");
  const interrupt = el("button", "mini", "Interrumpir");
  interrupt.type = "button";
  interrupt.disabled = !["running", "waiting_input"].includes(agent.status);
  interrupt.addEventListener("click", () => interruptAgent(agent));
  actions.append(interrupt);

  const pin = el("button", "mini", state.pinned.includes(agent.id) ? "Desfijar" : "Fijar");
  pin.type = "button";
  pin.addEventListener("click", () => togglePin(agent));
  actions.append(pin);

  const eye = el(
    "button",
    "mini",
    state.hidden.has(agent.id) ? "Mostrar" : "Ocultar"
  );
  eye.type = "button";
  eye.addEventListener("click", () => toggleAgent(agent));
  actions.append(eye);

  const folder = el("button", "mini", "Abrir carpeta");
  folder.type = "button";
  folder.disabled = !agent.cwd;
  folder.addEventListener("click", () => openAgentFolder(agent));
  actions.append(folder);

  const copy = el("button", "mini", "Copiar ID");
  copy.type = "button";
  copy.addEventListener("click", () => copyAgentId(agent));
  actions.append(copy);

  body.append(detailSection("Acciones", actions));

  const message = document.createElement("textarea");
  message.id = "drawer-message";
  message.className = "detail-message";
  message.placeholder = "Escribe una instrucción para este agente…";
  message.value = state.drawerDraft;
  message.addEventListener("input", () => {
    state.drawerDraft = message.value;
  });

  const send = el("button", "button", "Enviar mensaje");
  send.type = "button";
  send.addEventListener("click", () => sendAgentMessage(agent, message));

  body.append(
    detailSection(
      "Mensaje",
      message,
      send,
      el("p", "muted", "Solo funciona con agentes que aceptan texto (OpenCode).")
    )
  );
}

async function interruptAgent(agent) {
  try {
    const result = await state.api.interrupt_agent(agent.id);
    if (!result || !result.ok) {
      showToast(`No se pudo interrumpir a ${agent.name}.`, "error");
      return;
    }
    showToast(`${agent.name} interrumpido.`, "done");
  } catch (error) {
    showToast("Error al interrumpir: " + String(error), "error");
  }
}

async function sendAgentMessage(agent, textarea) {
  const text = textarea.value.trim();
  if (!text) return;
  try {
    const result = await state.api.send_agent_text(agent.id, text);
    if (!result || !result.ok) {
      showToast(
        result && result.error === "agent_unsupported"
          ? `${agent.name} no acepta mensajes.`
          : `No se pudo enviar el mensaje a ${agent.name}.`,
        "error"
      );
      return;
    }
    state.drawerDraft = "";
    textarea.value = "";
    showToast(`Mensaje enviado a ${agent.name}.`, "done");
  } catch (error) {
    showToast("Error al enviar el mensaje: " + String(error), "error");
  }
}

async function openAgentFolder(agent) {
  try {
    const result = await state.api.open_folder(agent.cwd);
    if (!result || !result.ok) {
      showToast("No se pudo abrir la carpeta del proyecto.", "error");
    }
  } catch (error) {
    showToast("Error al abrir la carpeta: " + String(error), "error");
  }
}

async function copyAgentId(agent) {
  try {
    await navigator.clipboard.writeText(agent.id);
    showToast("ID copiado al portapapeles.", "done");
    return;
  } catch {
    /* WebView sin permisos de portapapeles: se intenta el método clásico. */
  }
  try {
    const helper = document.createElement("textarea");
    helper.value = agent.id;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    document.body.append(helper);
    helper.select();
    document.execCommand("copy");
    helper.remove();
    showToast("ID copiado al portapapeles.", "done");
  } catch {
    showToast("No se pudo copiar el ID.", "error");
  }
}

/* -- acciones masivas y atajos ---------------------------------------- */

async function showAllAgents() {
  for (const agentId of [...state.hidden]) {
    await state.api.set_visibility(agentId, false);
  }
  await refresh();
}

async function hideAllAgents() {
  if (!window.confirm("¿Ocultar todos los agentes del hardware?")) return;
  for (const agent of state.agents) {
    await state.api.set_visibility(agent.id, true);
  }
  await refresh();
}

async function clearAllPins() {
  for (const agentId of [...state.pinned]) {
    await state.api.set_pinned(agentId, false);
  }
  await refresh();
}

function globalShortcuts(event) {
  if (event.key === "Escape" && state.detailId) {
    closeDrawer();
    return;
  }

  const tag = (document.activeElement?.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return;

  if (event.key === "/") {
    event.preventDefault();
    $("agent-search").focus();
  } else if (event.key.toLowerCase() === "r") {
    refresh();
  }
}

async function togglePin(agent) {
  const willPin = !state.pinned.includes(agent.id);
  const pinned = state.agents.filter((item) => state.pinned.includes(item.id)).length;
  if (willPin && pinned >= 2) {
    showBanner("Máximo 2 agentes fijados. Desfija uno antes de fijar otro.");
    return;
  }
  try {
    const result = await state.api.set_pinned(agent.id, willPin);
    if (!result || !result.ok) {
      showBanner(
        result && result.error === "pin_limit"
          ? "Máximo 2 agentes fijados. Desfija uno antes de fijar otro."
          : "No se pudo guardar el fijado."
      );
      return;
    }
    state.pinned = Array.isArray(result.pinned) ? result.pinned : [];
    hideBanner();
    render();
  } catch (error) {
    showBanner("Error al fijar el agente: " + String(error));
  }
}

async function toggleAgent(agent) {
  const willHide = !state.hidden.has(agent.id);
  try {
    const result = await state.api.set_visibility(agent.id, willHide);
    if (!result || !result.ok) {
      showBanner("No se pudo guardar el cambio de visibilidad.");
      return;
    }
    if (willHide) state.hidden.add(agent.id);
    else state.hidden.delete(agent.id);
    render();
  } catch (error) {
    showBanner("Error al cambiar la visibilidad: " + String(error));
  }
}

function showBanner(text) {
  const banner = $("banner");
  banner.textContent = text;
  banner.hidden = false;
}

function hideBanner() {
  $("banner").hidden = true;
}

boot();
