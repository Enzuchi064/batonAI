"use strict";

/* Simulador del dispositivo batonAI.
   Pantalla de 480×320, tres botones (B, A, PTT) y encoder, conectados al mismo
   protocolo que usará el firmware. */

const TOKEN_KEY = "batonai.token";
const DEVICE_KEY = "batonai.device";
const STATUS = {
  IDLE: "en espera",
  RUNNING: "trabajando",
  WAITING_INPUT: "te necesita",
  DONE: "terminado",
  ERROR: "error",
  OFFLINE: "sin conexión",
};
const RISK_SHORT = {
  low: "bajo",
  normal: "normal",
  high: "alto",
  critical: "crítico",
};
const RISK_LEVEL = { low: 1, normal: 2, high: 3, critical: 4 };
const LOGO_PATHS = {
  anthropic:
    "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z",
  openai:
    "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z",
  gemini:
    "M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81",
  antigravity:
    "M89.6992 93.695C94.3659 97.195 101.366 94.8617 94.9492 88.445C75.6992 69.7783 79.7825 18.445 55.8659 18.445C31.9492 18.445 36.0325 69.7783 16.7825 88.445C9.78251 95.445 17.3658 97.195 22.0325 93.695C40.1159 81.445 38.9492 59.8617 55.8659 59.8617C72.7825 59.8617 71.6159 81.445 89.6992 93.695Z",
  github:
    "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
};

function logoSvg(agent) {
  const key = (agent.provider || "").toLowerCase();
  if (key === "anthropic" || key === "claude") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#D97757" d="${LOGO_PATHS.anthropic}"/></svg>`;
  }
  if (key === "openai" || key === "codex") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#E6E6E6" d="${LOGO_PATHS.openai}"/></svg>`;
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
  return null;
}

function iconNode(agent, className = "icon") {
  const svg = logoSvg(agent);
  if (svg) {
    const node = el("span", className);
    node.innerHTML = svg;
    return node;
  }
  return el("span", `${className} plain`, (agent.name || "?").charAt(0).toUpperCase());
}

function pinSvg() {
  return `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 5 3 3v2H7v-2l3-3-1-5Z"/><path d="M12 13v8"/></svg>`;
}

function applyLogo(node, agent) {
  const svg = logoSvg(agent);
  node.className = "icon";
  if (svg) {
    node.innerHTML = svg;
    return;
  }
  node.classList.add("plain");
  node.textContent = (agent.name || "?").charAt(0).toUpperCase();
}
// Sin STT todavía: el dictado simulado rota estas frases para validar el flujo
// PTT → preview → envío.
const TRANSCRIPTS = [
  "Ejecuta los tests de autenticación",
  "Revisa el último cambio del parser",
  "Añade un test para el caso de error",
  "¿Qué falta para cerrar esta tarea?",
];

const money = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "USD",
  currencyDisplay: "narrowSymbol",
  minimumFractionDigits: 2,
});
const integer = new Intl.NumberFormat("es-ES");

const app = {
  token: null,
  deviceId: null,
  virtual: null,
  virtualPoll: null,
  ws: null,
  connected: false,
  retry: 0,
  agents: [],
  system: {},
  limits: {
    ok: false,
    providers: [],
    period: "all",
    view: "remaining",
    selected_windows: null,
    error: "not_read",
  },

  hidden: new Set(),
  statuses: new Map(),
  pinned: [],
  approvals: [],
  selected: null,
  current: null,
  focus: "allow",
  detail: null,
  local: {},
  preview: null,
  transcriptIndex: 0,
  recording: false,
  recTimer: 0,
  recStart: 0,
  speech: null,
  speechText: "",
  speechError: false,
  speechStopping: false,
  speechDone: false,
  speechUnavailable: false,
  speechDenied: false,
  speechTimer: 0,
  holdMs: 0,
  holding: false,
  holdRAF: 0,
  holdTimer: 0,
  sending: false,
  noticeTimer: 0,
  rollerOffset: 0,
  dragX: null,
  dragMoved: 0,
  rest: {
    active: false,
    summary: null,
    startedAt: 0,
    snapshot: null,
    pending: 0,
    summaryTimer: 0,
  },
  restAfterMs: 5 * 60 * 1000,
  restOverride: false,
  lastInputAt: Date.now(),
  restTimer: 0,
};

const $ = (id) => document.getElementById(id);

/* -- aviso sonoro ------------------------------------------------------ */

let audioCtx = null;

function unlockAudio() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  if (!audioCtx) audioCtx = new Ctx();
  if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
  return audioCtx;
}

function bell(ctx) {
  const now = ctx.currentTime;
  // Dos notas cortas, tipo campana: 880 Hz + su quinta.
  for (const [freq, volume, duration] of [[880, 0.12, 0.55], [1318.5, 0.06, 0.4]]) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, now);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(volume, now + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + duration + 0.03);
  }
}

function playDing() {
  const ctx = unlockAudio();
  if (!ctx) return;
  if (ctx.state === "running") bell(ctx);
  else ctx.resume().then(() => bell(ctx)).catch(() => {});
}

window.addEventListener("pointerdown", unlockAudio, { passive: true });
window.addEventListener("keydown", unlockAudio);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setLink(text, state) {
  const link = $("link");
  link.textContent = text;
  link.dataset.state = state;
  $("device").classList.toggle("is-offline", state === "off");
  $("led").dataset.state = state;
  app.connected = state === "on";
  if (app.rest.active) renderRest();
}

/* -- arranque --------------------------------------------------------- */

async function boot() {
  initRest();
  app.deviceId = sessionStorage.getItem(DEVICE_KEY) || panelDeviceId();
  app.token = loadStoredToken();
  await deviceBoot();
  restoreRest();
}

function panelDeviceId() {
  let id = sessionStorage.getItem(DEVICE_KEY);
  if (!id) {
    const random = (crypto.randomUUID?.() || Math.random().toString(36).slice(2))
      .replace(/[^a-zA-Z0-9]/g, "")
      .slice(0, 12);
    id = `baton-web-${random}`;
    sessionStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

function loadStoredToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return sessionStorage.getItem(TOKEN_KEY);
  }
}

function storeToken(token) {
  try { localStorage.setItem(TOKEN_KEY, token); } catch { /* sin localStorage */ }
  sessionStorage.setItem(TOKEN_KEY, token);
}

function clearStoredToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* sin localStorage */ }
  sessionStorage.removeItem(TOKEN_KEY);
}

function isLoopbackPanel() {
  const host = location.hostname;
  return host === "127.0.0.1" || host === "::1" || host === "localhost";
}

async function fetchVirtual() {
  try {
    const response = await fetch("/api/dev/virtual", { cache: "no-store" });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchPanelToken() {
  try {
    const response = await fetch("/api/dev/virtual/panel-token", {
      cache: "no-store",
    });
    if (!response.ok) return null;
    const data = await response.json();
    return data.token || null;
  } catch {
    return null;
  }
}

async function deviceBoot() {
  const state = await fetchVirtual();
  if (!state) {
    // Gateway antiguo o sin dispositivo virtual: se usa el bootstrap de siempre.
    await bootstrap();
    return;
  }

  app.virtual = state;
  app.deviceId = state.device_id;
  sessionStorage.setItem(DEVICE_KEY, state.device_id);
  $("device-short").textContent = state.short || "—";

  // Panel local: token de desarrollo sin interacción. Panel remoto: token
  // guardado tras vincular con Google Authenticator. Si no hay ninguno, se
  // muestra el QR y el campo del código.
  let token = isLoopbackPanel() ? await fetchPanelToken() : null;
  if (!token) token = loadStoredToken();
  if (token) {
    app.token = token;
    storeToken(token);
    hideVirtualPairing();
    connect();
    return;
  }

  showVirtualPairing(state);
}

async function bootstrap() {
  try {
    const response = await fetch(
      `/api/dev/bootstrap?device_id=${encodeURIComponent(app.deviceId || panelDeviceId())}`
    );
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    app.token = data.token;
    app.deviceId = data.device_id || app.deviceId;
    storeToken(data.token);
    sessionStorage.setItem(DEVICE_KEY, app.deviceId);
    if (data.state) renderState(data.state);
    connect();
  } catch {
    notify("No se pudo emparejar con el gateway.");
  }
}

function showVirtualPairing(state) {
  const pairing = $("pairing");
  pairing.hidden = false;

  $("pairing-state").textContent = state.needs_confirm ? "confirmar" : "esperando";
  const qr = $("pairing-qr");
  if (qr.dataset.qr !== state.qr_svg) {
    qr.innerHTML = state.qr_svg || "";
    qr.dataset.qr = state.qr_svg || "";
  }
  $("pairing-device").textContent = state.short
    ? `BATON-${state.short}`
    : state.device_id;
  $("pairing-confirm").hidden = !state.needs_confirm;
  const linkedTo =
    state.paired_to && state.paired_to !== "Panel web"
      ? state.paired_to
      : "";
  $("pairing-hint").textContent = state.needs_confirm
    ? state.paired_to
      ? `Confirma en el dispositivo para reemplazar ${state.paired_to}.`
      : "Confirma en el dispositivo para emparejar."
    : linkedTo
      ? `Escanea el QR y escribe el código para abrir ${linkedTo}.`
      : "Escanea el QR con Google Authenticator y escribe aquí el código.";
  $("pairing-form").hidden = Boolean(state.needs_confirm);

  if (state.needs_confirm) {
    $("pairing-pc").textContent = state.pending_pc || "PC";
    $("pairing-sas").textContent = state.sas || "0000";
  }

  startVirtualPoll();
}

function startVirtualPoll() {
  if (app.virtualPoll) return;
  app.virtualPoll = setInterval(pollVirtual, 1000);
}

function stopVirtualPoll() {
  if (!app.virtualPoll) return;
  clearInterval(app.virtualPoll);
  app.virtualPoll = null;
}

async function pollVirtual() {
  const state = await fetchVirtual();
  if (!state) return;
  app.virtual = state;

  if (state.paired) {
    const token = isLoopbackPanel() ? await fetchPanelToken() : null;
    if (token) {
      stopVirtualPoll();
      app.token = token;
      storeToken(token);
      hideVirtualPairing();
      connect();
      return;
    }
  }

  showVirtualPairing(state);
}

function hideVirtualPairing() {
  $("pairing").hidden = true;
  $("pairing-error").hidden = true;
  $("pairing-error").textContent = "";
  stopVirtualPoll();
}

const PAIR_ERRORS = {
  bad_code: "Código incorrecto. Prueba con el siguiente.",
  rate_limited: "Demasiados intentos. Espera un minuto.",
  replay: "Ese código ya se usó. Espera al siguiente.",
  not_paired: "El panel todavía no está vinculado.",
};

function showPairingError(text) {
  const node = $("pairing-error");
  node.textContent = text;
  node.hidden = !text;
}

async function selfPair() {
  const input = $("pairing-code");
  const code = String(input.value || "").replace(/\D/g, "").slice(0, 6);
  if (code.length !== 6) {
    showPairingError("Escribe los 6 dígitos de Google Authenticator.");
    return;
  }
  const button = $("pairing-submit");
  button.disabled = true;
  showPairingError("");
  try {
    const response = await fetch("/api/dev/virtual/self-pair", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (!response.ok) {
      let detail = "pair_failed";
      try {
        detail = String((await response.json()).detail || detail);
      } catch { /* respuesta sin JSON */ }
      showPairingError(
        PAIR_ERRORS[detail] || "No se pudo vincular este panel."
      );
      return;
    }
    const data = await response.json();
    if (!data.token) {
      showPairingError("El gateway no devolvió el token del panel.");
      return;
    }
    app.token = data.token;
    storeToken(data.token);
    input.value = "";
    hideVirtualPairing();
    connect();
  } catch {
    showPairingError("No se pudo contactar con el gateway.");
  } finally {
    button.disabled = false;
  }
}

function controlHeaders(extra = {}) {
  const headers = { ...extra };
  if (app.token) headers.Authorization = `Bearer ${app.token}`;
  return headers;
}

async function confirmOnDevice() {
  const pairId = app.virtual && app.virtual.pair_id;
  if (!pairId) return;
  try {
    const response = await fetch("/api/dev/virtual/confirm", {
      method: "POST",
      headers: controlHeaders({ "content-type": "application/json" }),
      body: JSON.stringify({ pair_id: pairId }),
    });
    if (!response.ok) {
      notify("No se pudo confirmar el emparejamiento.");
      return;
    }
    await pollVirtual();
  } catch {
    notify("No se pudo contactar con el gateway.");
  }
}

async function cancelOnDevice() {
  try {
    await fetch("/api/dev/virtual/cancel", {
      method: "POST",
      headers: controlHeaders(),
    });
  } catch { /* se reintenta en el siguiente sondeo */ }
  await pollVirtual();
}

/* -- modo reposo ------------------------------------------------------- */

const REST_KEY = "baton.rest";
const REST_DEFAULT_MS = 5 * 60 * 1000;

function initRest() {
  const param = new URLSearchParams(location.search).get("rest");
  if (param !== null) {
    const seconds = Number(param);
    app.restAfterMs =
      Number.isFinite(seconds) && seconds > 0
        ? Math.min(seconds, 3600) * 1000
        : 0;
    app.restOverride = true;
  } else {
    setInterval(loadRestConfig, 30000);
  }

  setInterval(loadLimits, 60000);
  updateHeaderClock();
  setInterval(updateHeaderClock, 30000);

  window.addEventListener("pointerdown", restInput, true);
  window.addEventListener("keydown", restInput, true);
  window.addEventListener("wheel", restInput, { capture: true, passive: false });
  window.addEventListener("touchstart", restInput, { capture: true, passive: false });

  setInterval(checkRest, 1000);
  setInterval(() => {
    if (app.rest.active && !app.rest.summary) renderRest();
  }, 1000);
}

async function loadRestConfig() {
  if (app.restOverride) return;
  try {
    const response = await fetch("/api/config/rest", {
      cache: "no-store",
      headers: controlHeaders(),
    });
    if (!response.ok) return;
    const data = await response.json();
    if (typeof data.rest_after_s === "number") {
      app.restAfterMs = Math.max(0, data.rest_after_s) * 1000;
    }
  } catch { /* se mantiene el valor por defecto */ }
}

async function loadLimits() {
  try {
    const response = await fetch("/api/limits", {
      cache: "no-store",
      headers: controlHeaders(),
    });
    if (!response.ok) return;
    const data = await response.json();
    app.limits = {
      ok: Boolean(data.ok),
      providers: Array.isArray(data.providers) ? data.providers : [],
      period: data.period || "all",
      view: data.view === "used" ? "used" : "remaining",
      selected_windows: Array.isArray(data.selected_windows)
        ? data.selected_windows
        : null,
      error: data.error || null,
    };
    renderDeviceLimits();
  } catch { /* la cinta muestra el último estado conocido */ }
}

function restInput(event) {
  if (event.target?.closest?.("#rest-now")) return;
  if (app.rest.summary) {
    event.preventDefault();
    event.stopImmediatePropagation();
    closeSummary();
    return;
  }
  if (app.rest.active) {
    event.preventDefault();
    event.stopImmediatePropagation();
    wakeRest();
    return;
  }
  app.lastInputAt = Date.now();
}

function checkRest() {
  if (app.rest.active || app.rest.summary) return;
  if (!app.restAfterMs) return;
  if (Date.now() - app.lastInputAt < app.restAfterMs) return;
  if (!$("pairing").hidden) return;
  if (app.current) return;
  if (!$("detail").hidden) return;
  if (!$("audit").hidden) return;
  if (app.recording) return;
  enterRest();
}

function snapshotForRest() {
  const agents = app.agents.map((agent) => ({
    id: agent.id,
    name: agent.name,
    status: agent.status,
    task: agent.task || "",
    cost_session: Number(agent.cost_session) || 0,
    tokens_session: Number(agent.tokens_session) || 0,
  }));
  return {
    agents,
    total_cost:
      Number(app.system.total_cost) ||
      agents.reduce((sum, agent) => sum + agent.cost_session, 0),
    total_tokens:
      Number(app.system.total_tokens) ||
      agents.reduce((sum, agent) => sum + agent.tokens_session, 0),
  };
}

function pendingApprovals() {
  return app.approvals.filter(
    (approval) => !app.hidden.has(approval.agent_id)
  ).length;
}

function setRestButton(mode) {
  const button = $("rest-now");
  if (!button) return;
  const labels = {
    idle: "modo reposo",
    sleeping: "despertar",
    summary: "cerrar resumen",
  };
  button.textContent = labels[mode] || labels.idle;
  button.dataset.active = String(mode !== "idle");
  button.setAttribute("aria-pressed", String(mode !== "idle"));
}

function toggleRest() {
  app.lastInputAt = Date.now();
  if (app.rest.summary) {
    closeSummary();
    return;
  }
  if (app.rest.active) {
    wakeRest();
    return;
  }
  enterRest();
}

function enterRest() {
  if (app.rest.active) return;
  app.rest.active = true;
  app.rest.startedAt = Date.now();
  app.rest.snapshot = snapshotForRest();
  app.rest.pending = pendingApprovals();
  app.rest.summary = null;

  $("rest").hidden = false;
  $("rest-sleep").hidden = false;
  $("rest-summary").hidden = true;
  setRestButton("sleeping");
  renderRest();
  persistRest();
}

function persistRest() {
  try {
    sessionStorage.setItem(
      REST_KEY,
      JSON.stringify({
        started_at: app.rest.startedAt,
        snapshot: app.rest.snapshot,
        pending: app.rest.pending,
      })
    );
  } catch { /* sin sessionStorage se sigue funcionando */ }
}

function restoreRest() {
  if (!app.restAfterMs || !$("pairing").hidden) return;
  let data = null;
  try {
    data = JSON.parse(sessionStorage.getItem(REST_KEY) || "null");
  } catch {
    return;
  }
  if (!data || !data.started_at || !data.snapshot) return;
  if (Date.now() - data.started_at > 24 * 3600 * 1000) {
    sessionStorage.removeItem(REST_KEY);
    return;
  }

  app.rest.active = true;
  app.rest.startedAt = data.started_at;
  app.rest.snapshot = data.snapshot;
  app.rest.pending = data.pending || 0;
  $("rest").hidden = false;
  $("rest-sleep").hidden = false;
  $("rest-summary").hidden = true;
  setRestButton("sleeping");
  renderRest();
}

function renderRest() {
  if (!app.rest.active || app.rest.summary) return;

  const now = new Date();
  $("rest-clock").textContent = new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(now);
  $("rest-date").textContent = (() => {
    const text = new Intl.DateTimeFormat("es-ES", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(now);
    return text.charAt(0).toUpperCase() + text.slice(1);
  })();

  const total = app.agents.length;
  const working = app.agents.filter((agent) => agent.status === "RUNNING").length;
  $("rest-state").textContent = app.connected
    ? total
      ? `${total} ${total === 1 ? "agente" : "agentes"} · ${working} trabajando`
      : "sin agentes"
    : "sin conexión";

  const pending = pendingApprovals();
  app.rest.pending = pending;
  $("rest-pending").hidden = pending === 0;
  $("rest-pending").textContent = pending
    ? `${pending} ${pending === 1 ? "permiso pendiente" : "permisos pendientes"}`
    : "";
}

function wakeRest() {
  if (!app.rest.active || app.rest.summary) return;
  app.rest.summary = computeSummary();
  $("rest-sleep").hidden = true;
  $("rest-summary").hidden = false;
  setRestButton("summary");
  renderSummary(app.rest.summary);

  app.lastInputAt = Date.now();
  clearTimeout(app.rest.summaryTimer);
  app.rest.summaryTimer = setTimeout(closeSummary, 12000);
}

function computeSummary() {
  const previous = new Map(
    (app.rest.snapshot?.agents || []).map((agent) => [agent.id, agent])
  );
  const events = [];
  let done = 0;
  let waiting = 0;
  let errors = 0;
  let offline = 0;
  let added = 0;

  const currentIds = new Set(app.agents.map((agent) => agent.id));

  for (const agent of app.agents) {
    const before = previous.get(agent.id);
    const hidden = app.hidden.has(agent.id);
    const suffix = hidden ? " · oculto" : "";

    if (!before) {
      added += 1;
      if (agent.status === "ERROR") {
        errors += 1;
        events.push({ kind: "error", text: `${agent.name} falló${suffix}` });
      } else if (agent.status === "WAITING_INPUT") {
        waiting += 1;
        events.push({
          kind: "waiting",
          text: `${agent.name} espera permiso${suffix}`,
        });
      } else if (agent.status === "OFFLINE") {
        offline += 1;
        events.push({
          kind: "offline",
          text: `${agent.name} se desconectó${suffix}`,
        });
      } else {
        events.push({ kind: "new", text: `${agent.name} es nuevo${suffix}` });
      }
      continue;
    }

    const wasActive =
      before.status === "RUNNING" || before.status === "WAITING_INPUT";

    if (wasActive && (agent.status === "DONE" || agent.status === "IDLE")) {
      done += 1;
      events.push({ kind: "done", text: `${agent.name} terminó${suffix}` });
    } else if (agent.status === "ERROR" && before.status !== "ERROR") {
      errors += 1;
      events.push({ kind: "error", text: `${agent.name} falló${suffix}` });
    }

    if (agent.status === "WAITING_INPUT") {
      waiting += 1;
      events.push({
        kind: "waiting",
        text: `${agent.name} espera permiso${suffix}`,
      });
    }

    if (agent.status === "OFFLINE" && before.status !== "OFFLINE") {
      offline += 1;
      events.push({
        kind: "offline",
        text: `${agent.name} se desconectó${suffix}`,
      });
    }
  }

  for (const [id, before] of previous) {
    if (!currentIds.has(id) && before.status !== "OFFLINE") {
      offline += 1;
      events.push({
        kind: "offline",
        text: `${before.name} se desconectó`,
      });
    }
  }

  const order = { error: 0, waiting: 1, done: 2, offline: 3, new: 4 };
  events.sort((left, right) => order[left.kind] - order[right.kind]);

  const currentCost =
    Number(app.system.total_cost) ||
    app.agents.reduce((sum, agent) => sum + (Number(agent.cost_session) || 0), 0);
  const beforeCost = Number(app.rest.snapshot?.total_cost) || 0;
  const currentTokens =
    Number(app.system.total_tokens) ||
    app.agents.reduce((sum, agent) => sum + (Number(agent.tokens_session) || 0), 0);
  const beforeTokens = Number(app.rest.snapshot?.total_tokens) || 0;

  return {
    awayMs: Date.now() - app.rest.startedAt,
    done,
    waiting,
    errors,
    offline,
    added,
    events,
    pending: pendingApprovals(),
    costDelta: currentCost - beforeCost,
    costNow: currentCost,
    tokensDelta: currentTokens - beforeTokens,
    tokensNow: currentTokens,
  };
}

function formatAway(ms) {
  const minutes = Math.max(1, Math.round(ms / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours < 24) return rest ? `${hours} h ${rest} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "desde ayer" : `hace ${days} días`;
}

function deltaText(value, current, formatter) {
  if (value > 0) return `+${formatter(value)}`;
  if (value < 0) return `total ${formatter(current)}`;
  return formatter(0);
}

function renderSummary(summary) {
  $("summary-away").textContent = formatAway(summary.awayMs);
  $("summary-done").textContent = String(summary.done);
  $("summary-waiting").textContent = String(summary.waiting);
  $("summary-errors").textContent = String(summary.errors);

  const list = $("summary-events");
  list.replaceChildren();
  const icons = {
    done: "✓",
    waiting: "!",
    error: "✗",
    offline: "·",
    new: "+",
  };
  for (const event of summary.events.slice(0, 3)) {
    const row = el("li");
    row.dataset.kind = event.kind;
    row.append(
      el("span", "summary-icon", icons[event.kind] || "·"),
      el("span", "summary-text", event.text)
    );
    list.append(row);
  }
  if (summary.events.length > 3) {
    list.append(
      el("li", "summary-more", `+${summary.events.length - 3} más`)
    );
  }

  $("summary-empty").hidden =
    summary.events.length > 0 || summary.pending > 0;

  const cost = deltaText(
    summary.costDelta,
    summary.costNow,
    (value) => money.format(value)
  );
  const tokens = deltaText(
    summary.tokensDelta,
    summary.tokensNow,
    (value) => integer.format(value)
  );
  $("summary-extra").textContent = `${cost} · ${tokens} tokens`;

  const pending = $("summary-pending");
  pending.hidden = summary.pending === 0;
  pending.textContent = summary.pending
    ? `${summary.pending} ${
        summary.pending === 1 ? "permiso pendiente" : "permisos pendientes"
      } · A para revisar`
    : "";

  const progress = $("summary-progress");
  progress.style.animation = "none";
  void progress.offsetWidth;
  progress.style.animation = "";
}

function closeSummary() {
  clearTimeout(app.rest.summaryTimer);
  app.rest.summaryTimer = 0;
  app.rest.summary = null;
  app.rest.active = false;
  app.rest.snapshot = null;

  $("rest").hidden = true;
  $("rest-sleep").hidden = false;
  $("rest-summary").hidden = true;
  sessionStorage.removeItem(REST_KEY);
  app.lastInputAt = Date.now();
  setRestButton("idle");

  renderGrid();
  updateCounts();
  renderTray();
}

/* -- conexión --------------------------------------------------------- */

function connect() {
  if (app.ws) {
    try { app.ws.close(); } catch { /* ignorado */ }
  }
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${scheme}://${location.host}/ws/control`);
  app.ws = ws;
  setLink("conectando…", "wait");

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        type: "hello",
        proto: 1,
        device_id: app.deviceId || panelDeviceId(),
        fw: "simulador-0.1.0",
        token: app.token,
      })
    );
  };

  ws.onmessage = (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    handle(message);
  };

  ws.onclose = (event) => {
    app.connected = false;
    setLink("sin conexión", "off");
    setDevEnabled(false);
    stopPtt(true);
    if (event.code === 4401) {
      app.token = null;
      clearStoredToken();
      deviceBoot();
      return;
    }
    if (event.code === 4409) {
      setLink("reemplazado por otra pestaña", "off");
      notify("Otra pestaña está usando este panel.");
      return;
    }
    const delay = Math.min(30000, 800 * 2 ** app.retry) + Math.random() * 400;
    app.retry = Math.min(app.retry + 1, 6);
    setTimeout(connect, delay);
  };
}

function send(payload) {
  if (!app.ws || app.ws.readyState !== WebSocket.OPEN) {
    notify("Sin conexión con el gateway.");
    return false;
  }
  app.ws.send(JSON.stringify(payload));
  return true;
}

/* -- mensajes --------------------------------------------------------- */

function handle(message) {
  switch (message.type) {
    case "welcome":
      app.connected = true;
      app.retry = 0;
      app.hidden = new Set(message.config?.hidden_agents || []);
      app.pinned = message.config?.pinned_agents || [];
      setLink("conectado", "on");
      setDevEnabled(true);
      loadRestConfig();
      loadLimits();
      break;

    case "state":
      renderState(message);
      break;

    case "visibility":
      app.hidden = new Set(message.hidden_agents || []);
      if (app.detail && app.hidden.has(app.detail)) closeDetail();
      updateCounts();
      renderGrid();
      renderTray();
      break;

    case "pinned":
      app.pinned = message.pinned_agents || [];
      updateCounts();
      renderGrid();
      renderTray();
      break;

    case "approval_request":
      app.approvals.push(message);
      renderTray();
      if (app.rest.active) {
        if (pendingApprovals() > 0) playDing();
        if (app.rest.summary) {
          app.rest.summary.pending = pendingApprovals();
          renderSummary(app.rest.summary);
        } else {
          renderRest();
        }
      }
      break;

    case "approval_result":
      app.approvals = app.approvals.filter(
        (approval) => approval.approval_id !== message.approval_id
      );
      app.sending = false;
      renderTray();
      if (app.rest.active) {
        if (app.rest.summary) {
          app.rest.summary.pending = pendingApprovals();
          renderSummary(app.rest.summary);
        } else {
          renderRest();
        }
      }
      if (!message.duplicate) notify(resultText(message));
      break;

    case "error":
      app.sending = false;
      notify(message.message || message.code);
      updateButtons();
      break;

    case "ack":
      if (message.ref === "inject_text" && !message.ok) {
        notify("No se pudo enviar el texto al agente.");
      }
      break;

    default:
      break;
  }
}

function resultText(message) {
  switch (message.status) {
    case "accepted": return "Permiso concedido.";
    case "rejected": return "Permiso denegado.";
    case "expired": return "La petición caducó sin respuesta.";
    case "stale": return "La petición quedó obsoleta.";
    default: return message.reason || "Petición resuelta.";
  }
}

/* -- estado ----------------------------------------------------------- */

function renderState(message) {
  noteStatuses(message.agents || []);
  app.agents = message.agents || [];
  app.system = message.system || {};
  updateDevControls();

  if (app.rest.active) {
    renderRest();
    return;
  }

  updateCounts();

  const visible = visibleAgents();
  const cost = visible.reduce((sum, agent) => sum + (agent.cost_session || 0), 0);
  const tokens = visible.reduce((sum, agent) => sum + (agent.tokens_session || 0), 0);
  $("total-cost").textContent = money.format(cost);
  $("total-tokens").textContent = integer.format(tokens);

  renderGrid();
}

function visibleAgents() {
  const visible = app.agents.filter((agent) => !app.hidden.has(agent.id));
  if (!app.pinned.length) return visible;

  const byId = new Map(visible.map((agent) => [agent.id, agent]));
  const pinned = app.pinned.map((id) => byId.get(id)).filter(Boolean);
  const used = new Set(pinned.map((agent) => agent.id));
  return [...pinned, ...visible.filter((agent) => !used.has(agent.id))];
}

function updateDevControls() {
  // Los botones de simulación solo tienen sentido con los agentes de demo.
  const fake = app.agents.some((agent) => !String(agent.id).includes(":"));
  for (const id of ["force-normal", "force-high"]) {
    const button = $(id);
    if (button) button.style.display = fake ? "" : "none";
  }
}

function noteStatuses(agents) {
  const previous = app.statuses;
  const next = new Map();
  let finished = false;

  for (const agent of agents) {
    const before = previous.get(agent.id);
    next.set(agent.id, agent.status);
    if (
      before &&
      (before === "RUNNING" || before === "WAITING_INPUT") &&
      (agent.status === "IDLE" || agent.status === "DONE") &&
      !app.hidden.has(agent.id)
    ) {
      finished = true;
    }
  }

  app.statuses = next;
  if (finished) playDing();
}

function renderGrid() {
  const visible = visibleAgents();
  if (!visible.some((agent) => agent.id === app.selected)) {
    app.selected = visible.length ? visible[0].id : null;
  }
  if (app.detail && app.hidden.has(app.detail)) closeDetail();

  const grid = $("agents");
  grid.replaceChildren();

  if (!visible.length) {
    grid.append(el("p", "rack-empty", "No hay agentes visibles."));
    renderDeviceLimits();
    return;
  }

  for (const agent of visible) grid.append(renderAgent(agent));
  for (let i = visible.length; i < 6; i++) grid.append(el("div", "slot"));

  if (app.detail) renderDetail(app.detail);
  renderDeviceLimits();
}

function resetText(resetsAt) {
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

function limitLevel(remaining) {
  if (remaining <= 20) return "low";
  if (remaining <= 50) return "warn";
  return "ok";
}

function deviceLimitEntries(data) {
  const selected =
    data.selected_windows === null ||
    data.selected_windows === undefined
      ? null
      : new Set(data.selected_windows);
  const entries = [];
  for (const provider of data.providers || []) {
    if (!provider.installed || !provider.ok) continue;
    for (const window of provider.windows || []) {
      if (selected && !selected.has(window.key)) continue;
      entries.push({ provider, window });
    }
  }
  return entries;
}

function renderDeviceLimits() {
  const box = $("device-limits");
  if (!box) return;
  const data = app.limits;
  const mode = data.view === "used" ? "used" : "remaining";
  const modeNode = $("limits-mode");
  if (modeNode) modeNode.textContent = mode === "used" ? "gastado" : "restante";

  const entries = deviceLimitEntries(data);
  box.replaceChildren();

  if (!entries.length) {
    box.append(
      el(
        "div",
        "device-limits-empty",
        "Sin límites seleccionados. Actívalos con el ojo en Ajustes."
      )
    );
    return;
  }

  for (const entry of entries) {
    const used = Math.max(
      0,
      Math.min(100, Number(entry.window.used_percent) || 0)
    );
    const remaining = Number.isFinite(
      Number(entry.window.remaining_percent)
    )
      ? Math.max(0, Math.min(100, Number(entry.window.remaining_percent)))
      : 100 - used;
    const value = mode === "used" ? used : remaining;
    const level = limitLevel(remaining);
    const row = el("div", "device-limit");
    row.dataset.level = level;
    row.dataset.provider = entry.provider.id;

    const top = el("div", "dl-top");
    const name = el("span", "dl-name");
    name.append(
      el("span", "dl-dot"),
      el("span", "dl-provider", entry.provider.label),
      el("span", "dl-window", entry.window.label || entry.window.id)
    );
    top.append(name, el("b", "dl-value", `${value}%`));

    const bar = el("div", "dl-bar");
    const fill = el("span");
    fill.style.width = `${value}%`;
    bar.append(fill);

    const reset = resetText(entry.window.resets_at);
    const foot = el("div", "dl-foot");
    foot.append(
      el("span", "", mode === "used" ? "usado" : "restante"),
      el("span", "reset", reset ? `↻ ${reset}` : "sin renovación")
    );

    row.append(top, bar, foot);
    box.append(row);
  }
}

function updateHeaderClock() {
  const node = $("head-clock");
  if (!node) return;
  node.textContent = new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function updateCounts() {
  const visible = visibleAgents();
  const count = (status) => visible.filter((a) => a.status === status).length;
  const waiting = count("WAITING_INPUT");
  const working = count("RUNNING");
  const idle = count("IDLE") + count("DONE");
  const problems = count("ERROR") + count("OFFLINE");

  $("count-waiting").textContent = waiting;
  $("count-working").textContent = working;
  $("count-idle").textContent = idle;
  $("count-error").textContent = problems;

  $("agent-total").textContent = visible.length;
  const word = $("agent-total-word");
  if (word) word.textContent = visible.length === 1 ? "agente" : "agentes";
  const total = Math.max(1, waiting + working + idle + problems);
  $("mix-waiting").style.width = `${(waiting / total) * 100}%`;
  $("mix-working").style.width = `${(working / total) * 100}%`;
  $("mix-idle").style.width = `${(idle / total) * 100}%`;
  $("mix-error").style.width = `${(problems / total) * 100}%`;

  document.querySelector('[data-count="waiting"]').classList.toggle("is-active", waiting > 0);
  document.querySelector('[data-count="working"]').classList.toggle("is-active", working > 0);
  document.querySelector('[data-count="idle"]').classList.toggle("is-active", idle > 0);
  document.querySelector('[data-count="error"]').classList.toggle("is-active", problems > 0);
}

function renderAgent(agent) {
  const label = STATUS[agent.status] || STATUS.OFFLINE;
  const pinned = app.pinned.includes(agent.id);
  const card = el("article", "agent");
  card.dataset.status = agent.status;
  card.dataset.id = agent.id;
  card.tabIndex = 0;
  card.setAttribute("aria-label", `${agent.name}: ${label}${pinned ? " · fijado" : ""}`);
  if (agent.id === app.selected) card.classList.add("is-selected");
  if (pinned) {
    card.classList.add("is-pinned");
  }

  const head = el("div", "agent-head");
  head.append(iconNode(agent));

  const identity = el("div", "agent-id");
  identity.append(
    el("div", "agent-name", agent.name),
    el("div", "agent-model", agent.model)
  );
  head.append(identity);

  const status = el("span", "status");
  if (pinned) {
    const mark = el("span", "pin-mark");
    mark.innerHTML = pinSvg();
    mark.title = "Fijado arriba";
    status.append(mark);
  }
  status.title = label;
  status.append(el("span", "dot"));
  head.append(status);

  const task = el("p", "task", agent.task || "Sin tarea activa.");
  const foot = el("div", "agent-foot");
  foot.append(
    el("span", null, formatDuration(agent.since)),
    el(
      "span",
      null,
      agent.cost_session > 0
        ? `${money.format(agent.cost_session)} · ${integer.format(agent.tokens_session)} tok`
        : "sin consumo"
    )
  );

  card.append(head, task, foot);
  card.addEventListener("click", () => {
    if (app.current || !$("audit").hidden) return;
    selectAgent(agent.id);
    openDetail(agent.id);
  });
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (app.current || !$("audit").hidden) return;
      selectAgent(agent.id);
      openDetail(agent.id);
    }
  });
  return card;
}

function selectAgent(agentId) {
  app.selected = agentId;
  document.querySelectorAll(".agent").forEach((card) => {
    const selected = card.dataset.id === agentId;
    card.classList.toggle("is-selected", selected);
    if (selected) {
      // La rejilla de 480×320 scrollea: el foco debe quedar siempre visible.
      card.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  });
}

function moveSelection(delta) {
  const agents = visibleAgents();
  if (!agents.length) return;
  const index = agents.findIndex((agent) => agent.id === app.selected);
  const next = (index + delta + agents.length) % agents.length;
  selectAgent(agents[next].id);
}

/* -- conversación del agente ------------------------------------------ */

function openDetail(agentId) {
  const agent = app.agents.find((item) => item.id === agentId);
  if (!agent) return;
  if (app.detail !== agentId) app.preview = null;
  app.detail = agentId;
  selectAgent(agentId);
  $("detail").hidden = false;
  renderDetail(agentId);
  $("conversation").scrollTop = $("conversation").scrollHeight;
}

function closeDetail() {
  app.detail = null;
  app.preview = null;
  $("detail").hidden = true;
  renderPreview();
}

function messageNode(kind, text) {
  const node = el("div", `msg ${kind}`);
  if (kind === "user") node.append(el("span", "who", "tú · voz"));
  node.append(el("p", null, text));
  return node;
}

function renderDetail(agentId) {
  const agent = app.agents.find((item) => item.id === agentId);
  if (!agent) {
    closeDetail();
    return;
  }
  const label = STATUS[agent.status] || STATUS.OFFLINE;
  applyLogo($("detail-icon"), agent);
  $("detail-name").textContent = agent.name;
  $("detail-model").textContent = agent.model;
  const state = $("detail-state");
  state.textContent = label;
  state.dataset.status = agent.status;
  $("detail-task").textContent = agent.task || "Sin tarea activa.";

  const conversation = $("conversation");
  const atBottom =
    conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 16;
  conversation.replaceChildren();
  conversation.append(
    messageNode(
      "system",
      `${agent.cwd || "directorio desconocido"} · ` +
      `${money.format(agent.cost_session || 0)} · ` +
      `${integer.format(agent.tokens_session || 0)} tok · ` +
      formatDuration(agent.since)
    )
  );

  const lines = (agent.log_tail || []).filter(Boolean);
  const injected = new Set();
  if (!lines.length) conversation.append(messageNode("system", "sin actividad reciente"));
  for (const line of lines) {
    if (line.startsWith("⌨ ")) {
      // El texto dictado se guarda en el log del agente: se pinta como mensaje
      // propio en su posición cronológica, no al final.
      const text = line.slice(2);
      injected.add(text);
      conversation.append(messageNode("user", text));
    } else {
      conversation.append(
        messageNode(/^[→✓✗⏹↳]/.test(line) ? "tool" : "agent", line)
      );
    }
  }
  for (const item of app.local[agentId] || []) {
    if (!injected.has(item.text)) conversation.append(messageNode("user", item.text));
  }

  if (atBottom) conversation.scrollTop = conversation.scrollHeight;
  renderPreview();
}

function renderPreview() {
  const box = $("preview");
  const preview = app.preview;
  if (!preview || !app.detail || preview.agentId !== app.detail) {
    box.hidden = true;
    if (!app.recording) $("composer-hint").textContent = "Mantén PTT para dictar";
    return;
  }
  box.hidden = false;
  $("preview-text").textContent = preview.text;
  $("composer-hint").textContent = "A envía · B cancela";
}

function sendDictation() {
  const preview = app.preview;
  if (!preview) return;
  const ok = send({
    type: "inject_text",
    agent_id: preview.agentId,
    text: preview.text,
    confirm: true,
  });
  if (!ok) return;
  (app.local[preview.agentId] ||= []).push({ text: preview.text, ts: Date.now() });
  app.preview = null;
  renderDetail(preview.agentId);
  notify("Texto enviado al agente (simulado).");
  const conversation = $("conversation");
  conversation.scrollTop = conversation.scrollHeight;
}

function cancelPreview() {
  app.preview = null;
  renderPreview();
}

/* -- bandeja de aprobación -------------------------------------------- */

function renderTray() {
  const tray = $("tray");
  const visibleApprovals = app.approvals.filter(
    (approval) => !app.hidden.has(approval.agent_id)
  );
  const approval = visibleApprovals[0];
  const previousId = app.current ? app.current.approval_id : null;
  app.current = approval || null;

  if (!approval) {
    tray.hidden = true;
    endHold();
    return;
  }

  tray.hidden = false;
  tray.dataset.risk = approval.risk;
  $("tray-agent").textContent = agentName(approval.agent_id);
  $("tray-title").textContent = approval.title;
  $("tray-command").textContent = approval.command;
  $("tray-cwd").textContent = approval.cwd || "directorio desconocido";

  const risk = $("tray-risk");
  risk.dataset.risk = approval.risk;
  risk.textContent = RISK_SHORT[approval.risk] || "normal";
  $("tray-level").textContent = `${RISK_LEVEL[approval.risk] || 2}/4`;
  $("tray-radar").style.setProperty("--hold", "0");

  const details =
    (approval.details && approval.details.length
      ? approval.details
      : approval.reasons) || [];
  const reasons = $("tray-reasons");
  reasons.replaceChildren();
  if (!details.length) {
    reasons.append(
      el("li", "", "No se reconoce como peligroso, pero puede modificar cosas.")
    );
  } else {
    for (const detail of details.slice(0, 3)) {
      reasons.append(el("li", "", detail));
    }
    if (details.length > 3) {
      reasons.append(el("li", "", `+${details.length - 3} más`));
    }
  }

  const queued = visibleApprovals.length - 1;
  $("tray-queue").textContent = queued > 0 ? `+${queued} en cola` : "";

  app.holdMs = approval.hold_ms || 0;
  if (approval.approval_id !== previousId) setFocus("allow");
  else updateHint();

  updateButtons();
  updateCountdown();
}

function updateButtons() {
  const blocked = app.sending || !app.current;
  $("confirm").disabled = blocked;
  $("back").disabled = blocked;
}

function setFocus(option) {
  app.focus = option === "deny" ? "deny" : "allow";
  $("opt-allow").classList.toggle("is-focused", app.focus === "allow");
  $("opt-deny").classList.toggle("is-focused", app.focus === "deny");
  updateHint();
}

function updateHint() {
  if (!app.current) return;
  let text;
  if (app.holdMs && app.focus === "allow") {
    text = `Mantén A ${(app.holdMs / 1000).toFixed(1)} s para confirmar «Permitir»`;
  } else {
    text = `A confirma «${app.focus === "deny" ? "Denegar" : "Permitir"}» · B vuelve`;
  }
  $("tray-hint").textContent = text;
}

function activateFocused() {
  if (app.focus === "deny") {
    respond("deny");
    return;
  }
  beginHold();
}

function agentName(agentId) {
  const agent = app.agents.find((item) => item.id === agentId);
  return agent ? agent.name : agentId;
}

function respond(optionId) {
  if (!app.current || app.sending) return;
  const sent = send({
    type: "approval_response",
    approval_id: app.current.approval_id,
    option_id: optionId,
    source: "button",
  });
  if (!sent) return;
  app.sending = true;
  updateButtons();
  // Si el resultado no llega, no dejamos la bandeja bloqueada.
  setTimeout(() => {
    app.sending = false;
    updateButtons();
  }, 2500);
}

function beginHold() {
  const approval = app.current;
  if (!approval || app.sending || app.holding) return;
  if (!app.holdMs) {
    respond("allow");
    return;
  }
  app.holding = true;
  const started = performance.now();
  const fill = $("hold-fill");
  const radar = $("tray-radar");
  // El envío va por temporizador: no depende de que el navegador repinte.
  app.holdTimer = setTimeout(() => {
    endHold();
    respond("allow");
  }, app.holdMs);
  const step = (now) => {
    if (!app.holding) return;
    const progress = Math.min(1, (now - started) / app.holdMs);
    fill.style.width = `${progress * 100}%`;
    radar.style.setProperty("--hold", String(progress));
    if (progress < 1) app.holdRAF = requestAnimationFrame(step);
  };
  app.holdRAF = requestAnimationFrame(step);
}

function endHold() {
  app.holding = false;
  clearTimeout(app.holdTimer);
  cancelAnimationFrame(app.holdRAF);
  $("hold-fill").style.width = "0%";
  const radar = $("tray-radar");
  if (radar) radar.style.setProperty("--hold", "0");
}

function updateCountdown() {
  const approval = app.current;
  if (!approval) return;
  const remaining = Math.max(0, (Date.parse(approval.expires_at) - Date.now()) / 1000);
  $("tray-countdown").textContent = remaining > 0
    ? `quedan ${Math.ceil(remaining)} s`
    : "caducada";

  if (remaining <= 0) {
    app.approvals = app.approvals.filter(
      (item) => item.approval_id !== approval.approval_id
    );
    renderTray();
    notify("La petición caducó sin respuesta.");
  }
}

/* -- acciones de los controles físicos -------------------------------- */

function pressA() {
  if (!$("pairing").hidden && app.virtual && app.virtual.needs_confirm) {
    confirmOnDevice();
    return;
  }
  if (app.preview) {
    sendDictation();
    return;
  }
  if (app.current) {
    if (app.focus === "deny") {
      respond("deny");
      return;
    }
    beginHold();
    return;
  }
  if (!$("audit").hidden) return;
  if (app.detail) return;
  if (app.selected) openDetail(app.selected);
}

function pressB() {
  if (!$("pairing").hidden && app.virtual && app.virtual.needs_confirm) {
    cancelOnDevice();
    return;
  }
  if (app.preview) {
    cancelPreview();
    return;
  }
  if (app.current) {
    respond("deny");
    return;
  }
  if (!$("audit").hidden) {
    toggleAudit();
    return;
  }
  if (app.detail) closeDetail();
}

function stepEncoder(delta) {
  if (!delta) return;

  app.rollerOffset -= delta * 6;
  $("roller").style.backgroundPositionX = `${app.rollerOffset}px`;

  if (app.current) {
    const options = ["allow", "deny"];
    const index = options.indexOf(app.focus);
    const next = (index + (delta > 0 ? 1 : -1) + options.length) % options.length;
    setFocus(options[next]);
    return;
  }
  if (!$("audit").hidden) {
    $("audit-body").scrollTop += delta * 24;
    return;
  }
  if (app.detail) {
    $("conversation").scrollTop += delta * 18;
    return;
  }
  moveSelection(delta);
}

/* -- PTT -------------------------------------------------------------- */

function startPtt() {
  if (app.recording) return;
  app.recording = true;
  app.recStart = performance.now();
  app.preview = null;
  app.speechText = "";
  app.speechError = false;
  app.speechStopping = false;
  app.speechDone = false;
  app.speechUnavailable = false;
  app.speechDenied = false;
  renderPreview();
  $("rec").hidden = false;
  $("rec-time").textContent = "0.0 s";
  $("pad-ptt").classList.add("is-down");
  $("ptt").classList.add("is-rec");
  if (app.detail) {
    $("composer-hint").textContent = "grabando…";
    startSpeech();
  }
  app.recTimer = setInterval(() => {
    const seconds = (performance.now() - app.recStart) / 1000;
    $("rec-time").textContent = `${seconds.toFixed(1)} s`;
  }, 100);
}

function startSpeech() {
  const Recognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    app.speechUnavailable = true;
    return;
  }

  try {
    const recognition = new Recognition();
    let finalText = "";
    recognition.lang = "es-ES";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index++) {
        const result = event.results[index];
        const text = result[0]?.transcript || "";
        if (result.isFinal) finalText += text + " ";
        else interim += text;
      }
      app.speechText = `${finalText}${interim}`.trim();
      if (app.detail) {
        $("composer-hint").textContent = app.speechText || "grabando…";
      }
    };

    recognition.onerror = (event) => {
      app.speechError = true;
      if (
        event.error === "not-allowed" ||
        event.error === "service-not-allowed"
      ) {
        app.speechDenied = true;
        notify("Micrófono no permitido. Actívalo en el navegador.");
      }
    };

    recognition.onend = () => {
      if (app.recording && !app.speechStopping && !app.speechError) {
        try {
          recognition.start();
        } catch {
          /* el motor ya se estaba reiniciando */
        }
        return;
      }
      if (app.speechStopping) finishPtt();
    };

    app.speech = recognition;
    recognition.start();
  } catch {
    app.speechUnavailable = true;
  }
}

function stopSpeech() {
  const recognition = app.speech;
  app.speech = null;
  app.speechStopping = false;
  app.speechDone = true;
  clearTimeout(app.speechTimer);
  if (recognition) {
    try {
      recognition.abort();
    } catch {
      /* noop */
    }
  }
}

function finishPtt() {
  if (app.speechDone) return;
  app.speechDone = true;
  app.speechStopping = false;
  clearTimeout(app.speechTimer);
  app.speech = null;

  if (!app.detail) return;
  const text = (app.speechText || "").trim();
  if (text) {
    app.preview = { agentId: app.detail, text };
    renderPreview();
    return;
  }
  if (app.speechError) notify("No se pudo transcribir el dictado.");
  else notify("No se entendió el dictado.");
  renderPreview();
}

function stopPtt(silent = false) {
  if (!app.recording) return;
  const held = performance.now() - app.recStart;
  app.recording = false;
  clearInterval(app.recTimer);
  $("rec").hidden = true;
  $("pad-ptt").classList.remove("is-down");
  $("ptt").classList.remove("is-rec");

  if (silent) {
    stopSpeech();
    renderPreview();
    return;
  }
  if (!app.connected) {
    stopSpeech();
    notify("Sin conexión con el gateway.");
    renderPreview();
    return;
  }
  if (!app.detail) {
    stopSpeech();
    notify("Abre un agente para dictar.");
    return;
  }
  if (held < 250) {
    stopSpeech();
    notify("Mantén PTT para dictar.");
    renderPreview();
    return;
  }

  if (app.speechDenied) {
    stopSpeech();
    notify("Micrófono bloqueado. Permite el micrófono en el navegador.");
    renderPreview();
    return;
  }

  if (app.speech && !app.speechError && !app.speechUnavailable) {
    app.speechStopping = true;
    try {
      app.speech.stop();
    } catch {
      finishPtt();
      return;
    }
    app.speechTimer = setTimeout(finishPtt, 1200);
    return;
  }

  if (app.speechError) {
    stopSpeech();
    notify("No se pudo transcribir el dictado.");
    renderPreview();
    return;
  }

  // Sin API de reconocimiento: mantener el simulador para revisar el flujo.
  const text = TRANSCRIPTS[app.transcriptIndex++ % TRANSCRIPTS.length];
  app.preview = { agentId: app.detail, text };
  if (app.speechUnavailable) {
    notify("Reconocimiento de voz no disponible; usando texto de ejemplo.");
  }
  renderPreview();
}

/* -- auditoría -------------------------------------------------------- */

async function toggleAudit() {
  const panel = $("audit");
  const toggle = $("audit-toggle");
  if (!panel.hidden) {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    return;
  }
  panel.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  await loadAudit();
}

async function loadAudit() {
  const body = $("audit-body");
  body.replaceChildren(el("p", "audit-empty", "Cargando…"));
  try {
    const response = await fetch("/api/audit?limit=40", {
      headers: controlHeaders(),
    });
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    body.replaceChildren();
    if (!data.approvals.length) {
      body.append(el("p", "audit-empty", "Sin aprobaciones registradas."));
      return;
    }
    for (const row of data.approvals) {
      const item = el("div", "audit-row");
      item.append(
        el("span", "audit-time", timeOf(row.created_at)),
        el("span", "audit-status", row.status),
        el("span", "audit-cmd", row.command)
      );
      item.querySelector(".audit-status").dataset.status = row.status;
      body.append(item);
    }
  } catch {
    body.replaceChildren(el("p", "audit-empty", "No se pudo leer la auditoría."));
  }
}

/* -- acciones de desarrollo ------------------------------------------- */

async function devAction(path, body) {
  if (!app.connected) {
    notify("Sin conexión con el gateway.");
    return;
  }
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: controlHeaders({ "content-type": "application/json" }),
      body: JSON.stringify(body || {}),
    });
    if (!response.ok) {
      notify(response.status === 409
        ? "Ya hay una petición en curso."
        : "El gateway rechazó la acción.");
    }
  } catch {
    notify("No se pudo contactar con el gateway.");
  }
}

function setDevEnabled(enabled) {
  $("force-normal").disabled = !enabled;
  $("force-high").disabled = !enabled;
}

/* -- utilidades ------------------------------------------------------- */

function notify(text) {
  const notice = $("notice");
  notice.textContent = text;
  notice.hidden = false;
  $("device").classList.add("has-notice");
  clearTimeout(app.noticeTimer);
  app.noticeTimer = setTimeout(() => {
    notice.hidden = true;
    $("device").classList.remove("has-notice");
  }, 3500);
}

function formatDuration(iso) {
  const seconds = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (seconds < 60) return `${Math.floor(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}

function timeOf(iso) {
  const date = new Date(iso);
  return date.toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function isTyping(target) {
  return target instanceof HTMLElement &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
}

/* -- listeners de la pantalla ----------------------------------------- */

$("opt-allow").addEventListener("click", () => setFocus("allow"));
$("opt-deny").addEventListener("click", () => setFocus("deny"));

$("confirm").addEventListener("pointerdown", (event) => {
  event.preventDefault();
  activateFocused();
});
["pointerup", "pointerleave", "pointercancel"].forEach((name) => {
  $("confirm").addEventListener(name, endHold);
});
$("confirm").addEventListener("click", () => {
  if (app.focus === "deny") {
    respond("deny");
  } else if (!app.holdMs) {
    respond("allow");
  }
});
$("back").addEventListener("click", () => respond("deny"));
$("detail-close").addEventListener("click", closeDetail);
$("preview-send").addEventListener("click", sendDictation);
$("preview-cancel").addEventListener("click", cancelPreview);

$("ptt").addEventListener("pointerdown", (event) => {
  event.preventDefault();
  startPtt();
});
["pointerup", "pointerleave", "pointercancel"].forEach((name) => {
  $("ptt").addEventListener(name, () => stopPtt());
});
$("ptt").addEventListener("keydown", (event) => {
  if (event.key === " " || event.key === "Enter") {
    event.preventDefault();
    startPtt();
  }
});
$("ptt").addEventListener("keyup", (event) => {
  if (event.key === " " || event.key === "Enter") stopPtt();
});
$("force-normal").addEventListener("click", () =>
  devAction("/api/dev/approval", { risk: "normal" })
);
$("force-high").addEventListener("click", () =>
  devAction("/api/dev/approval", { risk: "high" })
);
$("audit-toggle").addEventListener("click", toggleAudit);
$("audit-close").addEventListener("click", toggleAudit);
$("rest-now").addEventListener("click", toggleRest);

$("pairing-submit").addEventListener("click", selfPair);
$("pairing-code").addEventListener("input", (event) => {
  event.target.value = event.target.value.replace(/\D/g, "").slice(0, 6);
});
$("pairing-code").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    selfPair();
  }
});

/* -- botones físicos -------------------------------------------------- */

const padA = $("pad-a");
const padB = $("pad-b");
const padPtt = $("pad-ptt");

padA.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  padA.classList.add("is-down");
  pressA();
});
["pointerup", "pointerleave", "pointercancel"].forEach((name) => {
  padA.addEventListener(name, () => {
    padA.classList.remove("is-down");
    endHold();
  });
});
padA.addEventListener("click", (event) => {
  if (event.detail === 0) pressA();
});

padB.addEventListener("pointerdown", () => padB.classList.add("is-down"));
["pointerup", "pointerleave", "pointercancel"].forEach((name) => {
  padB.addEventListener(name, () => padB.classList.remove("is-down"));
});
padB.addEventListener("click", pressB);

padPtt.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  startPtt();
});
["pointerup", "pointerleave", "pointercancel"].forEach((name) => {
  padPtt.addEventListener(name, () => stopPtt());
});
padPtt.addEventListener("keydown", (event) => {
  if (event.key === " " || event.key === "Enter") {
    event.preventDefault();
    startPtt();
  }
});
padPtt.addEventListener("keyup", (event) => {
  if (event.key === " " || event.key === "Enter") stopPtt();
});

/* -- encoder ---------------------------------------------------------- */

const encoder = $("encoder");
const STEP_PX = 18;

encoder.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  encoder.setPointerCapture(event.pointerId);
  app.dragX = event.clientX;
  app.dragMoved = 0;
});

encoder.addEventListener("pointermove", (event) => {
  if (app.dragX === null) return;
  let dx = event.clientX - app.dragX;
  while (Math.abs(dx) >= STEP_PX) {
    const direction = dx > 0 ? 1 : -1;
    stepEncoder(direction);
    app.dragX += direction * STEP_PX;
    app.dragMoved += STEP_PX;
    dx = event.clientX - app.dragX;
  }
});

function endEncoderDrag(event) {
  if (app.dragX === null) return;
  const wasTap = app.dragMoved === 0;
  app.dragX = null;
  try { encoder.releasePointerCapture(event.pointerId); } catch { /* ignorado */ }
  if (wasTap) {
    const rect = encoder.getBoundingClientRect();
    stepEncoder(event.clientX < rect.left + rect.width / 2 ? -1 : 1);
  }
}

encoder.addEventListener("pointerup", endEncoderDrag);
encoder.addEventListener("pointercancel", endEncoderDrag);
encoder.addEventListener("pointerleave", (event) => {
  if (event.buttons === 0) endEncoderDrag(event);
});

encoder.addEventListener("wheel", (event) => {
  event.preventDefault();
  stepEncoder(event.deltaY > 0 ? 1 : -1);
}, { passive: false });

encoder.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    stepEncoder(-1);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    stepEncoder(1);
  }
});

// La rueda sobre el dashboard también recorre los agentes; la rejilla se
// desplaza sola para mantener el foco visible.
$("agents").addEventListener("wheel", (event) => {
  event.preventDefault();
  stepEncoder(event.deltaY > 0 ? 1 : -1);
}, { passive: false });

/* -- teclado ---------------------------------------------------------- */

window.addEventListener("keydown", (event) => {
  if (isTyping(event.target)) return;
  const key = event.key.toLowerCase();
  if (key === "a") {
    if (!event.repeat) pressA();
  } else if (key === "b") {
    pressB();
  } else if (key === "enter") {
    if (!event.repeat) pressA();
  } else if (key === "arrowleft") {
    event.preventDefault();
    stepEncoder(-1);
  } else if (key === "arrowright") {
    event.preventDefault();
    stepEncoder(1);
  } else if (key === "escape") {
    if (!$("audit").hidden) toggleAudit();
    else if (app.detail) closeDetail();
  }
});

window.addEventListener("keyup", (event) => {
  if (event.key.toLowerCase() === "a") endHold();
});

window.addEventListener("blur", () => {
  endHold();
  stopPtt(true);
});

setInterval(updateCountdown, 1000);

boot();
