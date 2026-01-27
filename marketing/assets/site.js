(function () {
  function sendEvent(name, meta) {
    var payload = {
      event: name,
      meta: meta || {},
      path: window.location.pathname,
      ref: document.referrer || null,
      ts: new Date().toISOString(),
    };
    var body = JSON.stringify(payload);
    if (navigator.sendBeacon) {
      try {
        navigator.sendBeacon("/api/marketing/track", body);
        return;
      } catch (e) {
        // fallback to fetch
      }
    }
    if (window.fetch) {
      fetch("/api/marketing/track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true,
      }).catch(function () {});
    }
  }

  function bindCtas() {
    var elements = document.querySelectorAll("[data-cta]");
    elements.forEach(function (el) {
      el.addEventListener("click", function () {
        var label = el.getAttribute("data-cta") || "cta";
        sendEvent("cta_click", { label: label, href: el.getAttribute("href") });
      });
    });
  }

  function bindForms() {
    var forms = document.querySelectorAll("[data-track-form]");
    forms.forEach(function (form) {
      form.addEventListener("submit", function () {
        var label = form.getAttribute("data-track-form") || "form";
        sendEvent("form_submit", { label: label });
      });
    });
  }

  function revealOnLoad() {
    var items = document.querySelectorAll(".reveal");
    items.forEach(function (item, idx) {
      item.style.setProperty("--delay", (idx * 0.08).toFixed(2) + "s");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindCtas();
    bindForms();
    revealOnLoad();
  });
})();
