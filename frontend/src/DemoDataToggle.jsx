export default function DemoDataToggle({ enabled, onToggle }) {
  return (
    <button className="btn secondary" onClick={onToggle}>
      {enabled ? "Hide demo data" : "Use demo data"}
    </button>
  );
}
