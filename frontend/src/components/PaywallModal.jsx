import PaywallCard from "./PaywallCard";

export default function PaywallModal({ open, onClose, ...props }) {
  if (!open) return null;
  return (
    <div className="paywall-overlay" role="dialog" aria-modal="true">
      <div className="paywall-modal">
        <PaywallCard {...props} isOpen={open} onDismiss={onClose} />
      </div>
    </div>
  );
}
