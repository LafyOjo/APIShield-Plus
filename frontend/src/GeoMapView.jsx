import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";

const CATEGORY_COLORS = {
  behaviour: "#3b82f6",
  login: "#10b981",
  threat: "#ef4444",
  error: "#f97316",
  audit: "#8b5cf6",
  default: "#64748b",
};

const LEGEND_BUCKETS = [
  { label: "Low", min: 1, max: 9 },
  { label: "Medium", min: 10, max: 49 },
  { label: "High", min: 50, max: 9999 },
];

const createClusterCustomIcon = (cluster) => {
  const count = cluster.getChildCount();
  let size = 32;
  let variant = "small";
  if (count >= 50) {
    size = 52;
    variant = "large";
  } else if (count >= 10) {
    size = 40;
    variant = "medium";
  }
  return L.divIcon({
    html: `<div class="map-cluster-inner">${count}</div>`,
    className: `map-cluster map-cluster-${variant}`,
    iconSize: L.point(size, size, true),
  });
};

const scaleRadius = (count) => {
  const base = 6;
  const scaled = base + Math.log(count + 1) * 4;
  return Math.min(22, Math.max(6, scaled));
};

const estimateRadiusKm = (count) => {
  if (!count || Number.isNaN(count)) return 80;
  const scaled = Math.sqrt(count) * 12;
  return Math.min(300, Math.max(60, scaled));
};

export default function GeoMapView({
  points,
  category,
  loading,
  error,
  planLimited,
  onSelect,
}) {
  const mapPoints = useMemo(
    () =>
      (points || []).filter(
        (point) => point.latitude != null && point.longitude != null
      ),
    [points]
  );
  const color = CATEGORY_COLORS[category] || CATEGORY_COLORS.default;
  const hasPoints = mapPoints.length > 0;

  const handleSelectPoint = (point) => {
    if (!onSelect) return;
    onSelect({
      type: "radius",
      lat: point.latitude,
      lon: point.longitude,
      radiusKm: estimateRadiusKm(point.count),
      label: point.city || point.country_code || "Unknown",
      count: point.count,
    });
  };

  const handleClusterClick = (event) => {
    if (!onSelect) return;
    const cluster = event.layer || event.target;
    const latlng = cluster?.getLatLng?.() || event.latlng;
    if (!latlng) return;
    const count = cluster?.getChildCount?.() || 0;
    onSelect({
      type: "radius",
      lat: latlng.lat,
      lon: latlng.lng,
      radiusKm: estimateRadiusKm(count),
      label: "Cluster",
      count,
    });
  };

  return (
    <div className="map-canvas">
      {hasPoints ? (
        <MapContainer
          center={[20, 0]}
          zoom={2}
          minZoom={2}
          scrollWheelZoom
          preferCanvas
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MarkerClusterGroup
            chunkedLoading
            iconCreateFunction={createClusterCustomIcon}
            eventHandlers={{ clusterclick: handleClusterClick }}
          >
            {mapPoints.map((point, idx) => (
              <CircleMarker
                key={`${point.latitude}-${point.longitude}-${idx}`}
                center={[point.latitude, point.longitude]}
                radius={scaleRadius(point.count)}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.6 }}
                eventHandlers={{ click: () => handleSelectPoint(point) }}
              >
                <Popup>
                  <strong>{point.count}</strong>{" "}
                  {point.city || point.country_code || "Unknown"}
                </Popup>
              </CircleMarker>
            ))}
          </MarkerClusterGroup>
        </MapContainer>
      ) : (
        <div className="map-empty">
          {planLimited
            ? "Upgrade your plan to unlock city-level map markers."
            : "No mappable coordinates yet for this time window."}
        </div>
      )}

      <div className="map-legend">
        <div className="map-legend-title">Activity</div>
        <div className="map-legend-row">
          {LEGEND_BUCKETS.map((bucket) => (
            <div key={bucket.label} className="map-legend-item">
              <span className="map-legend-dot" style={{ background: color }} />
              <span className="map-legend-label">
                {bucket.label} ({bucket.min}+)
              </span>
            </div>
          ))}
        </div>
        <div className="map-legend-note">
          Category: {category || "behaviour"}
        </div>
      </div>

      {loading && <div className="map-overlay">Loading summary...</div>}
      {error && !loading && <div className="map-overlay error-text">{error}</div>}
    </div>
  );
}
