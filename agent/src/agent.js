const EVENT_TYPES = {
  PAGE_VIEW: "page_view",
  CLICK: "click",
  SCROLL: "scroll",
  FORM_SUBMIT: "form_submit",
  ERROR: "error",
};

const SESSION_STORAGE_KEY = "__api_shield_session_id";
const DEFAULT_MAX_META_BYTES = 4096;
const DEFAULT_QUEUE_LIMIT = 200;
const DEFAULT_FLUSH_INTERVAL_MS = 3000;
const DEFAULT_FLUSH_MAX_EVENTS = 20;
const DEFAULT_SCROLL_STEP = 10;
const DEFAULT_SCROLL_THROTTLE_MS = 1000;
const DEFAULT_INCLUDE_STACK_HINTS = true;
const DEFAULT_COMPRESS_PAYLOAD = true;
const DEFAULT_COMPRESS_THRESHOLD_BYTES = 1024;
const DEFAULT_RETRY_MAX_ATTEMPTS = 3;
const DEFAULT_RETRY_BACKOFF_MS = 1000;
const DEFAULT_RETRY_MAX_DELAY_MS = 10000;
const DEFAULT_RETRY_JITTER_MS = 200;

const META_ALLOWLIST = {
  [EVENT_TYPES.CLICK]: ["tag", "id", "classes"],
  [EVENT_TYPES.SCROLL]: ["depth"],
  [EVENT_TYPES.FORM_SUBMIT]: ["form_id", "form_name", "form_action", "form_method"],
  [EVENT_TYPES.ERROR]: ["message", "source", "lineno", "colno", "reason"],
  [EVENT_TYPES.PAGE_VIEW]: [],
};

function isBrowser() {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

function nowIso() {
  return new Date().toISOString();
}

function uuidv4() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  const bytes =
    typeof crypto !== "undefined" && crypto.getRandomValues
      ? crypto.getRandomValues(new Uint8Array(16))
      : Array.from({ length: 16 }, () => Math.floor(Math.random() * 256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function safeSessionStorage() {
  try {
    return window.sessionStorage;
  } catch (_err) {
    return null;
  }
}

function getOrCreateSessionId() {
  const storage = safeSessionStorage();
  if (storage) {
    const existing = storage.getItem(SESSION_STORAGE_KEY);
    if (existing) {
      return existing;
    }
    const created = `s_${uuidv4()}`;
    storage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  }
  if (!getOrCreateSessionId._fallback) {
    getOrCreateSessionId._fallback = `s_${uuidv4()}`;
  }
  return getOrCreateSessionId._fallback;
}

function resolveApiKey(explicitKey) {
  if (explicitKey) {
    return explicitKey;
  }
  if (!isBrowser()) {
    return null;
  }
  if (window.__API_SHIELD_KEY__) {
    return window.__API_SHIELD_KEY__;
  }
  const current = document.currentScript;
  if (current && current.dataset && current.dataset.key) {
    return current.dataset.key;
  }
  const script = document.querySelector("script[data-key]");
  if (script && script.dataset && script.dataset.key) {
    return script.dataset.key;
  }
  return null;
}

function resolveIngestUrl(explicitUrl) {
  if (explicitUrl) {
    return explicitUrl;
  }
  if (!isBrowser()) {
    return "/api/v1/ingest/browser";
  }
  if (window.__API_SHIELD_INGEST_URL__) {
    return window.__API_SHIELD_INGEST_URL__;
  }
  const current = document.currentScript;
  if (current && current.dataset && current.dataset.endpoint) {
    return current.dataset.endpoint;
  }
  const script = document.querySelector("script[data-endpoint]");
  if (script && script.dataset && script.dataset.endpoint) {
    return script.dataset.endpoint;
  }
  const buildUrl =
    typeof __AGENT_INGEST_URL__ !== "undefined" ? __AGENT_INGEST_URL__ : "";
  return buildUrl || "/api/v1/ingest/browser";
}

function supportsCompression() {
  return (
    typeof CompressionStream !== "undefined" &&
    typeof Blob !== "undefined" &&
    typeof Response !== "undefined"
  );
}

async function encodePayload(payload, headers, config, state) {
  const text = JSON.stringify(payload);
  if (!config.compressPayload || !state.supportsCompression) {
    return { body: text, headers };
  }
  if (text.length < config.compressThresholdBytes) {
    return { body: text, headers };
  }
  try {
    const stream = new Blob([text], { type: "application/json" })
      .stream()
      .pipeThrough(new CompressionStream("gzip"));
    const buffer = await new Response(stream).arrayBuffer();
    return {
      body: buffer,
      headers: { ...headers, "Content-Encoding": "gzip" },
    };
  } catch (_err) {
    return { body: text, headers };
  }
}

function detectStackHints() {
  if (!isBrowser()) {
    return null;
  }
  const hints = {
    nextjs_detected: false,
    shopify_detected: false,
    wordpress_detected: false,
    react_spa_detected: false,
    laravel_detected: false,
    django_detected: false,
    rails_detected: false,
    custom_detected: false,
  };

  try {
    if (window.__NEXT_DATA__ || document.getElementById("__NEXT_DATA__")) {
      hints.nextjs_detected = true;
    }
  } catch (_err) {
    // ignore
  }

  try {
    const generator = document.querySelector("meta[name='generator']");
    const content = generator && generator.content ? generator.content.toLowerCase() : "";
    if (content.includes("wordpress")) {
      hints.wordpress_detected = true;
    }
    if (content.includes("shopify")) {
      hints.shopify_detected = true;
    }
  } catch (_err) {
    // ignore
  }

  try {
    if (window.Shopify) {
      hints.shopify_detected = true;
    }
  } catch (_err) {
    // ignore
  }

  try {
    const wpAsset = document.querySelector("script[src*='wp-content'],link[href*='wp-content']");
    if (wpAsset) {
      hints.wordpress_detected = true;
    }
  } catch (_err) {
    // ignore
  }

  try {
    if (document.getElementById("root") || document.getElementById("app")) {
      hints.react_spa_detected = true;
    }
  } catch (_err) {
    // ignore
  }

  const hasSignal = Object.values(hints).some(Boolean);
  if (!hasSignal) {
    hints.custom_detected = true;
  }
  return hints;
}

function normalizeUrl(rawUrl, dropQuery) {
  try {
    const url = new URL(rawUrl, window.location.href);
    url.hash = "";
    if (dropQuery) {
      url.search = "";
    }
    return url.toString();
  } catch (_err) {
    return rawUrl;
  }
}

function normalizePath(rawUrl) {
  try {
    const url = new URL(rawUrl, window.location.href);
    return url.pathname || "/";
  } catch (_err) {
    if (rawUrl && rawUrl.startsWith("/")) {
      return rawUrl.split("#")[0].split("?")[0];
    }
    return "/";
  }
}

function clampMeta(meta, maxBytes) {
  if (!meta) {
    return null;
  }
  try {
    const payload = JSON.stringify(meta);
    if (payload.length <= maxBytes) {
      return meta;
    }
  } catch (_err) {
    return {};
  }
  return {};
}

function sanitizeMeta(eventType, meta, allowlist, maxBytes) {
  if (!meta) {
    return null;
  }
  const allowed = allowlist[eventType] || [];
  if (allowed.length === 0) {
    return null;
  }
  const sanitized = {};
  for (const key of allowed) {
    if (meta[key] !== undefined && meta[key] !== null) {
      sanitized[key] = meta[key];
    }
  }
  return clampMeta(sanitized, maxBytes);
}

function pickClasses(element) {
  if (!element || typeof element.className !== "string") {
    return undefined;
  }
  const value = element.className.trim();
  if (!value) {
    return undefined;
  }
  return value.split(/\s+/).slice(0, 6).join(" ");
}

function getFormAction(form) {
  if (!form || !form.action) {
    return undefined;
  }
  try {
    const url = new URL(form.action, window.location.href);
    url.hash = "";
    url.search = "";
    return url.toString();
  } catch (_err) {
    return form.action.split("#")[0].split("?")[0];
  }
}

function createAgent(userConfig = {}) {
  const config = {
    flushIntervalMs: DEFAULT_FLUSH_INTERVAL_MS,
    flushMaxEvents: DEFAULT_FLUSH_MAX_EVENTS,
    maxQueueSize: DEFAULT_QUEUE_LIMIT,
    scrollStep: DEFAULT_SCROLL_STEP,
    scrollThrottleMs: DEFAULT_SCROLL_THROTTLE_MS,
    maxMetaBytes: DEFAULT_MAX_META_BYTES,
    dropUrlQuery: true,
    allowBatch: true,
    includeStackHints: DEFAULT_INCLUDE_STACK_HINTS,
    compressPayload: DEFAULT_COMPRESS_PAYLOAD,
    compressThresholdBytes: DEFAULT_COMPRESS_THRESHOLD_BYTES,
    maxRetryAttempts: DEFAULT_RETRY_MAX_ATTEMPTS,
    retryBackoffMs: DEFAULT_RETRY_BACKOFF_MS,
    retryMaxDelayMs: DEFAULT_RETRY_MAX_DELAY_MS,
    retryJitterMs: DEFAULT_RETRY_JITTER_MS,
    metaAllowlist: META_ALLOWLIST,
    ...userConfig,
  };

  const state = {
    apiKey: resolveApiKey(config.apiKey),
    ingestUrl: resolveIngestUrl(config.ingestUrl),
    supportsBatch: true,
    queue: [],
    flushTimer: null,
    flushPromise: null,
    lastUrl: null,
    lastScrollSentAt: 0,
    lastScrollPercent: 0,
    active: false,
    stackHints: config.includeStackHints ? detectStackHints() : null,
    supportsCompression: supportsCompression(),
    retryCounts: new Map(),
    retryTimer: null,
    retryDelayMs: config.retryBackoffMs,
  };

  function buildEvent(type, meta, referrerOverride) {
    if (!isBrowser()) {
      return null;
    }
    const url = normalizeUrl(window.location.href, config.dropUrlQuery);
    const path = normalizePath(url);
    const referrer =
      referrerOverride !== undefined
        ? referrerOverride
        : document.referrer || undefined;
    const sanitizedMeta = sanitizeMeta(
      type,
      meta,
      config.metaAllowlist,
      config.maxMetaBytes,
    );
    const payload = {
      event_id: uuidv4(),
      ts: nowIso(),
      type,
      url,
      path,
      referrer,
      session_id: getOrCreateSessionId(),
      meta: sanitizedMeta,
    };
    if (
      config.includeStackHints &&
      type === EVENT_TYPES.PAGE_VIEW &&
      state.stackHints
    ) {
      payload.stack_hints = state.stackHints;
    }
    return payload;
  }

  function enqueueEvent(event) {
    if (!event) {
      return;
    }
    if (state.queue.length >= config.maxQueueSize) {
      state.queue.shift();
    }
    state.queue.push(event);
    if (config.onEnqueue) {
      config.onEnqueue(event);
    }
    if (state.queue.length >= config.flushMaxEvents) {
      flush();
    }
  }

  function shouldRetryResponse(resp) {
    if (!resp) {
      return true;
    }
    if (resp.status >= 500) {
      return true;
    }
    return resp.status === 429 || resp.status === 408;
  }

  function resetRetryBackoff() {
    state.retryDelayMs = config.retryBackoffMs;
    if (state.retryTimer) {
      clearTimeout(state.retryTimer);
      state.retryTimer = null;
    }
  }

  function markRetrySuccess(events) {
    for (const event of events) {
      if (event && event.event_id) {
        state.retryCounts.delete(event.event_id);
      }
    }
  }

  function enqueueRetry(events) {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      state.queue.unshift(events[i]);
    }
    if (state.queue.length > config.maxQueueSize) {
      state.queue.length = config.maxQueueSize;
    }
  }

  function scheduleRetry(events) {
    const retryable = [];
    for (const event of events) {
      if (!event || !event.event_id) {
        continue;
      }
      const attempts = (state.retryCounts.get(event.event_id) || 0) + 1;
      if (attempts > config.maxRetryAttempts) {
        state.retryCounts.delete(event.event_id);
        continue;
      }
      state.retryCounts.set(event.event_id, attempts);
      retryable.push(event);
    }
    if (!retryable.length) {
      return;
    }
    enqueueRetry(retryable);
    if (state.retryTimer) {
      return;
    }
    const jitter =
      config.retryJitterMs > 0
        ? Math.floor(Math.random() * config.retryJitterMs)
        : 0;
    const delay = Math.min(state.retryDelayMs, config.retryMaxDelayMs) + jitter;
    state.retryTimer = setTimeout(() => {
      state.retryTimer = null;
      state.retryDelayMs = Math.min(
        state.retryDelayMs * 2,
        config.retryMaxDelayMs,
      );
      flush();
    }, delay);
  }

  async function sendEvents(events, useKeepalive) {
    if (!events.length) {
      return true;
    }
    const baseHeaders = {
      "Content-Type": "application/json",
      "X-Api-Key": state.apiKey,
    };
    if (state.supportsBatch && config.allowBatch && events.length > 1) {
      const { body, headers } = await encodePayload(
        { events },
        baseHeaders,
        config,
        state,
      );
      const resp = await fetch(state.ingestUrl, {
        method: "POST",
        headers,
        body,
        keepalive: useKeepalive,
      }).catch(() => null);
      if (resp && resp.ok) {
        markRetrySuccess(events);
        resetRetryBackoff();
        return true;
      }
      if (resp && [400, 404, 415, 422].includes(resp.status)) {
        state.supportsBatch = false;
      }
      if (resp && [401, 403].includes(resp.status)) {
        return false;
      }
      if (shouldRetryResponse(resp)) {
        scheduleRetry(events);
        return false;
      }
    }
    const failedEvents = [];
    for (const event of events) {
      const { body, headers } = await encodePayload(
        event,
        baseHeaders,
        config,
        state,
      );
      const resp = await fetch(state.ingestUrl, {
        method: "POST",
        headers,
        body,
        keepalive: useKeepalive,
      }).catch(() => null);
      if (resp && resp.ok) {
        markRetrySuccess([event]);
        continue;
      }
      if (shouldRetryResponse(resp)) {
        failedEvents.push(event);
      }
    }
    if (failedEvents.length) {
      scheduleRetry(failedEvents);
      return false;
    }
    resetRetryBackoff();
    return true;
  }

  function flush(options = {}) {
    if (!state.apiKey || !state.ingestUrl || !state.queue.length) {
      return;
    }
    if (state.flushPromise) {
      return;
    }
    const events = state.queue.splice(0, state.queue.length);
    const useKeepalive = Boolean(options.keepalive);
    state.flushPromise = sendEvents(events, useKeepalive)
      .catch(() => null)
      .finally(() => {
        state.flushPromise = null;
      });
  }

  function trackPageView(referrerOverride) {
    enqueueEvent(buildEvent(EVENT_TYPES.PAGE_VIEW, null, referrerOverride));
  }

  function trackClick(event) {
    if (!event || event.button !== 0) {
      return;
    }
    const target = event.target && event.target.nodeType === 1 ? event.target : null;
    const meta = {
      tag: target ? target.tagName.toLowerCase() : undefined,
      id: target && target.id ? target.id : undefined,
      classes: pickClasses(target),
    };
    enqueueEvent(buildEvent(EVENT_TYPES.CLICK, meta));
  }

  function trackScroll() {
    const now = Date.now();
    if (now - state.lastScrollSentAt < config.scrollThrottleMs) {
      return;
    }
    const doc = document.documentElement;
    const maxScroll = doc.scrollHeight - doc.clientHeight;
    if (maxScroll <= 0) {
      return;
    }
    const percent = Math.min(100, Math.round((window.scrollY / maxScroll) * 100));
    if (percent < state.lastScrollPercent + config.scrollStep) {
      return;
    }
    state.lastScrollSentAt = now;
    state.lastScrollPercent = percent;
    enqueueEvent(buildEvent(EVENT_TYPES.SCROLL, { depth: percent }));
  }

  function resetScrollTracking() {
    state.lastScrollPercent = 0;
    state.lastScrollSentAt = 0;
  }

  function trackFormSubmit(event) {
    const form = event.target;
    if (!form || form.nodeName !== "FORM") {
      return;
    }
    const meta = {
      form_id: form.id || undefined,
      form_name: form.name || undefined,
      form_action: getFormAction(form),
      form_method: form.method ? form.method.toLowerCase() : undefined,
    };
    enqueueEvent(buildEvent(EVENT_TYPES.FORM_SUBMIT, meta));
  }

  function trackError(event) {
    const meta = {
      message: event.message ? String(event.message).slice(0, 300) : undefined,
      source: event.filename ? String(event.filename).slice(0, 200) : undefined,
      lineno: event.lineno,
      colno: event.colno,
    };
    enqueueEvent(buildEvent(EVENT_TYPES.ERROR, meta));
  }

  function trackRejection(event) {
    const reason =
      event && event.reason ? String(event.reason).slice(0, 300) : "unhandledrejection";
    enqueueEvent(buildEvent(EVENT_TYPES.ERROR, { reason }));
  }

  function captureNavigation() {
    const currentUrl = normalizeUrl(window.location.href, config.dropUrlQuery);
    if (state.lastUrl === null) {
      state.lastUrl = currentUrl;
      trackPageView(undefined);
      return;
    }
    if (currentUrl !== state.lastUrl) {
      const referrer = state.lastUrl;
      state.lastUrl = currentUrl;
      resetScrollTracking();
      trackPageView(referrer);
    }
  }

  function start() {
    if (state.active) {
      return;
    }
    if (!state.apiKey || !state.ingestUrl) {
      return;
    }
    state.active = true;
    if (config.flushIntervalMs > 0) {
      state.flushTimer = window.setInterval(() => flush(), config.flushIntervalMs);
    }
    captureNavigation();
    document.addEventListener("click", trackClick, true);
    window.addEventListener("scroll", trackScroll, { passive: true });
    document.addEventListener("submit", trackFormSubmit, true);
    window.addEventListener("error", trackError);
    window.addEventListener("unhandledrejection", trackRejection);
    window.addEventListener("popstate", captureNavigation);

    const originalPushState = history.pushState;
    history.pushState = function (...args) {
      const result = originalPushState.apply(this, args);
      captureNavigation();
      return result;
    };
    const originalReplaceState = history.replaceState;
    history.replaceState = function (...args) {
      const result = originalReplaceState.apply(this, args);
      captureNavigation();
      return result;
    };

    window.addEventListener("pagehide", () => flush({ keepalive: true }));
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        flush({ keepalive: true });
      }
    });
  }

  function stop() {
    if (!state.active) {
      return;
    }
    state.active = false;
    if (state.flushTimer) {
      window.clearInterval(state.flushTimer);
      state.flushTimer = null;
    }
    document.removeEventListener("click", trackClick, true);
    window.removeEventListener("scroll", trackScroll);
    document.removeEventListener("submit", trackFormSubmit, true);
    window.removeEventListener("error", trackError);
    window.removeEventListener("unhandledrejection", trackRejection);
    window.removeEventListener("popstate", captureNavigation);
  }

  return {
    start,
    stop,
    flush,
    trackPageView,
    getSessionId: getOrCreateSessionId,
    _queue: state.queue,
  };
}

function initAgent(config) {
  const agent = createAgent(config);
  if (isBrowser()) {
    agent.start();
  }
  return agent;
}

if (isBrowser() && !window.__API_SHIELD_DISABLE_AUTO_INIT__) {
  window.APIShieldAgent = initAgent();
}

export { createAgent, initAgent, EVENT_TYPES };
