import { useEffect, useRef, useState } from "react";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import type { Institution, NetworkRow } from "./research-types";

const POINTS = "sugar-network-points";
const LINES = "sugar-network-lines";

export type MapMode = "points" | "heat";
export type Line = { from: [number, number]; to: [number, number] };

const roleOf = (networks: NetworkRow[], name: string) => networks.find((n) => n.name === name)?.role ?? "subject";

function pointCollection(rows: Institution[], networks: NetworkRow[]) {
  return {
    type: "FeatureCollection" as const,
    features: rows.filter((r) => r.placed && r.latitude !== null && r.longitude !== null).map((r) => ({
      type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [r.longitude as number, r.latitude as number] },
      properties: { id: r.entity_id, name: r.name, status: r.status, role: roleOf(networks, r.network), confidence: r.confidence.level, weight: 1 + r.activity.recent_items * 2 + r.programs.length },
    })),
  };
}
const lineCollection = (lines: Line[]) => ({ type: "FeatureCollection" as const, features: lines.map((l) => ({ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: [l.from, l.to] }, properties: {} })) });

/** Subject and reference institutions on one map: color by role, grey when closed, optional activity heat and nearest-reference lines. */
export function NetworkMap({ rows, networks, mode, lines, selectedId, onSelect, dark }: {
  rows: Institution[]; networks: NetworkRow[]; mode: MapMode; lines: Line[]; selectedId: string; onSelect: (id: string) => void; dark: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const select = useRef(onSelect);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { select.current = onSelect; }, [onSelect]);

  useEffect(() => {
    if (!container.current || map.current) return;
    let disposed = false;
    let instance: MapLibreMap | null = null;
    void import("maplibre-gl").then((maplibregl) => {
      if (disposed || !container.current) return;
      maplibregl.setWorkerUrl(workerUrl);
      const m = new maplibregl.Map({ container: container.current, style: "https://tiles.openfreemap.org/styles/liberty", center: [20, 25], zoom: 1.6, minZoom: 1, maxZoom: 17, attributionControl: false, cooperativeGestures: true });
      instance = m; map.current = m;
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      m.on("error", () => { if (!m.isStyleLoaded()) setError("The basemap is unavailable. Institution locations remain available in the list view."); });
      m.once("load", () => {
        setError("");
        m.addSource(LINES, { type: "geojson", data: lineCollection([]) });
        m.addLayer({ id: "overlap-lines", type: "line", source: LINES, paint: { "line-color": "#8b68c8", "line-width": 1.4, "line-dasharray": [2, 2], "line-opacity": 0.8 } });
        m.addSource(POINTS, { type: "geojson", data: pointCollection([], []), cluster: true, clusterMaxZoom: 11, clusterRadius: 40 });
        m.addLayer({ id: "heat", type: "heatmap", source: POINTS, filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "role"], "subject"]], layout: { visibility: "none" },
          paint: { "heatmap-weight": ["interpolate", ["linear"], ["get", "weight"], 1, 0.2, 10, 1], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 1, 12, 8, 40],
            "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "#fde7b0", 0.5, "#f4a259", 0.8, "#d9534f", 1, "#8a1c1c"], "heatmap-opacity": 0.85 } });
        m.addLayer({ id: "clusters", type: "circle", source: POINTS, filter: ["has", "point_count"], paint: { "circle-color": "#52667f", "circle-radius": ["step", ["get", "point_count"], 16, 15, 21, 50, 27], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
        m.addLayer({ id: "cluster-count", type: "symbol", source: POINTS, filter: ["has", "point_count"], layout: { "text-field": "{point_count_abbreviated}", "text-size": 12, "text-font": ["Noto Sans Bold"] }, paint: { "text-color": "#fff" } });
        m.addLayer({ id: "points", type: "circle", source: POINTS, filter: ["!", ["has", "point_count"]], paint: {
          "circle-color": ["case", ["in", ["get", "status"], ["literal", ["closed"]]], "#98a2b0", ["==", ["get", "role"], "reference"], "#1f8f6a", "#d2691e"],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 5, 9, 9], "circle-stroke-width": ["case", ["==", ["get", "confidence"], "low"], 2.2, 1.5],
          "circle-stroke-color": ["case", ["==", ["get", "confidence"], "low"], "#e0a800", "#ffffff"] } });
        m.addLayer({ id: "selected", type: "circle", source: POINTS, filter: ["==", ["get", "id"], ""], paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#2f6bcb", "circle-stroke-width": 3 } });
        m.addLayer({ id: "labels", type: "symbol", source: POINTS, minzoom: 6, filter: ["!", ["has", "point_count"]], layout: { "text-field": ["get", "name"], "text-size": 11, "text-offset": [0, 1.3], "text-anchor": "top", "text-font": ["Noto Sans Regular"], "text-max-width": 14 },
          paint: { "text-color": "#24354b", "text-halo-color": "#fff", "text-halo-width": 1.3 } });
        m.on("click", "clusters", (event) => {
          const feature = event.features?.[0];
          if (!feature || feature.geometry.type !== "Point") return;
          void (m.getSource(POINTS) as GeoJSONSource).getClusterExpansionZoom(Number(feature.properties?.cluster_id)).then((zoom) => m.easeTo({ center: feature.geometry.type === "Point" ? (feature.geometry.coordinates as [number, number]) : [0, 0], zoom })).catch(() => undefined);
        });
        m.on("click", "points", (event) => { const id = event.features?.[0]?.properties?.id; if (id) select.current(String(id)); });
        m.on("mouseenter", "points", () => { m.getCanvas().style.cursor = "pointer"; });
        m.on("mouseleave", "points", () => { m.getCanvas().style.cursor = ""; });
        setReady(true);
      });
    }).catch(() => { if (!disposed) setError("The map could not start. Use the list view."); });
    return () => { disposed = true; instance?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const data = pointCollection(rows, networks);
    (m.getSource(POINTS) as GeoJSONSource).setData(data);
    (m.getSource(LINES) as GeoJSONSource).setData(lineCollection(lines));
    const heat = mode === "heat";
    m.setLayoutProperty("heat", "visibility", heat ? "visible" : "none");
    for (const layer of ["clusters", "cluster-count", "points"]) m.setLayoutProperty(layer, "visibility", "visible");
    m.setPaintProperty("points", "circle-opacity", heat ? 0.55 : 1);
  }, [rows, networks, lines, mode, ready]);

  useEffect(() => { if (ready && map.current) map.current.setFilter("selected", ["==", ["get", "id"], selectedId || ""]); }, [selectedId, ready]);

  const fitted = useRef("");
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const pts = rows.filter((r) => r.placed && r.latitude !== null && r.longitude !== null);
    const key = pts.map((p) => p.entity_id).sort().join(",");
    if (!pts.length || key === fitted.current) return;
    fitted.current = key;
    const lons = pts.map((p) => p.longitude as number), lats = pts.map((p) => p.latitude as number);
    m.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 70, maxZoom: 6, duration: 400 });
  }, [rows, ready]);

  return (
    <div className={`map-frame network-map ${dark ? "dark" : ""}`}>
      <div ref={container} className="map-canvas" role="application" aria-label="Map of institutions. The list view has the same information." />
      {error && <div className="map-fallback"><span className="status-dot warn" />{error}</div>}
    </div>
  );
}
