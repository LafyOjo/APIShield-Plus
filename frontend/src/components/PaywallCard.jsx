import { useEffect, useRef, useState } from "react";
import { logPaywallEvent, startCheckout } from "../paywall";

const DEFAULT_BULLETS = [
  "Unlock advanced filters and deeper insights.",
  "Export richer data for analysis.",
  "Activate proactive protection workflows.",
];

export default function PaywallCard({
  title,
  subtitle,
  bullets = DEFAULT_BULLETS,
  previewTitle = "Preview",
  preview,
  ctaLabel = "Upgrade",
  dismissLabel = "Not now",
  onDismiss,
  onUpgrade,
  featureKey,
  source,
  planKey = "pro",
  showDismiss = true,
  isOpen = true,
  className = "",
}) {
  const [upgradeError, setUpgradeError] = useState("");
  const hasLoggedRef = useRef(false);

  useEffect(() => {
    if (!isOpen || !featureKey) return;
    if (hasLoggedRef.current) return;
    hasLoggedRef.current = true;
    logPaywallEvent({ featureKey, source, action: "shown" });
  }, [featureKey, isOpen, source]);

  const handleUpgrade = async () => {
    setUpgradeError("");
    if (featureKey) {
      await logPaywallEvent({ featureKey, source, action: "cta_clicked" });
    }
    const started = await startCheckout({ planKey, featureKey, source });
    if (!started) {
      setUpgradeError("Unable to start checkout. Visit billing to upgrade.");
    }
    if (onUpgrade) onUpgrade();
  };

  const handleDismiss = () => {
    if (featureKey) {
      logPaywallEvent({ featureKey, source, action: "dismissed" });
    }
    if (onDismiss) onDismiss();
  };

  return (
    <div className={`paywall-card ${className}`.trim()}>
      <div className="paywall-header">
        <div>
          <div className="paywall-kicker">Upgrade required</div>
          <h3 className="paywall-title">{title || "Unlock this feature"}</h3>
          {subtitle && <p className="subtle">{subtitle}</p>}
        </div>
        <span className="badge pro">{String(planKey || "pro").toUpperCase()}</span>
      </div>

      {bullets && bullets.length > 0 && (
        <ul className="paywall-bullets">
          {bullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
      )}

      {preview && (
        <div className="paywall-preview">
          <div className="paywall-preview-title">{previewTitle}</div>
          <div className="paywall-preview-body">{preview}</div>
        </div>
      )}

      {upgradeError && <div className="error-text">{upgradeError}</div>}

      <div className="paywall-actions">
        <button className="btn primary" onClick={handleUpgrade}>
          {ctaLabel}
        </button>
        {showDismiss && (
          <button className="btn secondary" onClick={handleDismiss}>
            {dismissLabel}
          </button>
        )}
      </div>
    </div>
  );
}
