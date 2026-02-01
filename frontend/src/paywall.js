import { apiFetch } from "./api";

export async function logPaywallEvent({ featureKey, source, action }) {
  if (!featureKey) return;
  try {
    await apiFetch("/api/v1/onboarding/feature-locked", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        feature_key: featureKey,
        source: source || null,
        action: action || "shown",
      }),
      skipReauth: true,
    });
  } catch (err) {
    // Ignore telemetry failures.
  }
}

export async function startCheckout({ planKey = "pro", featureKey, source }) {
  if (!planKey) {
    window.location.assign("/billing");
    return false;
  }
  try {
    const resp = await apiFetch("/api/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_key: planKey }),
    });
    if (!resp.ok) {
      return false;
    }
    const data = await resp.json();
    if (!data?.checkout_url) {
      return false;
    }
    await logPaywallEvent({ featureKey, source, action: "checkout_started" });
    window.location.assign(data.checkout_url);
    return true;
  } catch (err) {
    return false;
  }
}
