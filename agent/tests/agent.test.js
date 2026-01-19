import assert from "node:assert/strict";
import { createAgent } from "../src/agent.js";

function createMockDom() {
  const listeners = {};
  const document = {
    referrer: "",
    visibilityState: "visible",
    documentElement: {
      scrollHeight: 2000,
      clientHeight: 1000,
    },
    currentScript: null,
    querySelector() {
      return null;
    },
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    removeEventListener(type) {
      delete listeners[type];
    },
    dispatch(type, event) {
      if (listeners[type]) {
        listeners[type](event);
      }
    },
  };

  const history = {
    pushState(_state, _title, url) {
      if (url) {
        window.location.href = new URL(url, window.location.href).toString();
      }
    },
    replaceState(_state, _title, url) {
      if (url) {
        window.location.href = new URL(url, window.location.href).toString();
      }
    },
  };

  const window = {
    location: { href: "https://example.com/" },
    scrollY: 0,
    sessionStorage: {
      store: new Map(),
      getItem(key) {
        return this.store.get(key) || null;
      },
      setItem(key, value) {
        this.store.set(key, value);
      },
    },
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    removeEventListener(type) {
      delete listeners[type];
    },
    setInterval(fn, ms) {
      return setInterval(fn, ms);
    },
    clearInterval(id) {
      clearInterval(id);
    },
    __API_SHIELD_KEY__: "pk_test",
    __API_SHIELD_INGEST_URL__: "https://api.example.com/ingest",
  };

  return { window, document, history, listeners };
}

async function runTests() {
  const { window, document, history } = createMockDom();
  global.window = window;
  global.document = document;
  global.history = history;
  global.fetch = async () => ({ ok: true, status: 200 });

  const agentA = createAgent({ flushIntervalMs: 0 });
  const sessionA = agentA.getSessionId();
  const agentB = createAgent({ flushIntervalMs: 0 });
  const sessionB = agentB.getSessionId();
  assert.equal(sessionA, sessionB, "session_id should persist in sessionStorage");

  let fetchCalls = 0;
  global.fetch = async () => {
    fetchCalls += 1;
    return { ok: true, status: 200 };
  };
  const agentInterval = createAgent({ flushIntervalMs: 10, flushMaxEvents: 5 });
  agentInterval.start();
  agentInterval._queue.push({
    event_id: "test-event",
    ts: new Date().toISOString(),
    type: "page_view",
    url: "https://example.com/",
    path: "/",
    session_id: "s_test",
  });
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.ok(fetchCalls >= 1, "flush should trigger on interval");
  agentInterval.stop();

  const agentNav = createAgent({ flushIntervalMs: 0 });
  agentNav.start();
  const before = agentNav._queue.length;
  history.pushState({}, "", "/next");
  const after = agentNav._queue.length;
  assert.ok(after > before, "page_view should be queued on pushState");
  agentNav.stop();

  console.log("agent tests passed");
}

runTests().catch((err) => {
  console.error(err);
  process.exit(1);
});
