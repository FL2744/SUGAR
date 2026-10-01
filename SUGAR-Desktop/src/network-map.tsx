import { useEffect, useRef, useState } from "react";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { GeoJSONSource, Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import type { Institution, NetworkRow, PostMap } from "./research-types";

const POINTS = "sugar-network-points";
const LINES = "sugar-network-lines";
const POSTS = "sugar-post-pins";
const TARGETS = "sugar-post-targets";
const FLOWS = "sugar-post-flows";

export type MapMode = "points" | "heat";
export type Basemap = "dark" | "streets" | "terrain";
export type Line = { from: [number, number]; to: [number, number] };
export type PostLayers = { posts: boolean; targets: boolean; flows: boolean; institutions: boolean };

const TERRAIN: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: { topo: { type: "raster", tiles: ["https://a.tile.opentopomap.org/{z}/{x}/{y}.png", "https://b.tile.opentopomap.org/{z}/{x}/{y}.png", "https://c.tile.opentopomap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 17,
    attribution: "© OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors" } },
  layers: [{ id: "topo", type: "raster", source: "topo" }],
};
const styleFor = (basemap: Basemap): string | StyleSpecification => basemap === "terrain" ? TERRAIN : basemap === "dark" ? "https://tiles.openfreemap.org/styles/dark" : "https://tiles.openfreemap.org/styles/liberty";

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
const postCollection = (posts: PostMap | null) => ({
  type: "FeatureCollection" as const,
  features: (posts?.pins || []).filter((p) => p.latitude !== null && p.longitude !== null).map((p) => ({
    type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [p.longitude as number, p.latitude as number] },
    properties: { id: p.item_id, placement: p.placement, verified: p.verified },
  })),
});
const targetCollection = (posts: PostMap | null) => ({ type: "FeatureCollection" as const, features: (posts?.targets || []).map((t) => ({ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [t.longitude, t.latitude] }, properties: { name: t.name, posts: t.posts } })) });
const flowCollection = (posts: PostMap | null) => ({ type: "FeatureCollection" as const, features: (posts?.flows || []).map((f) => ({ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: [f.from, f.to] }, properties: { posts: f.posts } })) });

/** Posts, institutions and targets on one map. Posts: yellow = posted from here, hollow = a place the text names (approximate). Targets: rings by country. */
export function NetworkMap({ rows, networks, mode, lines, selectedId, onSelect, basemap, posts, layers, selectedPost, onSelectPost }: {
  rows: Institution[]; networks: NetworkRow[]; mode: MapMode; lines: Line[]; selectedId: string; onSelect: (id: string) => void; basemap: Basemap;
  posts: PostMap | null; layers: PostLayers; selectedPost: string; onSelectPost: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const select = useRef(onSelect);
  const selectPost = useRef(onSelectPost);
  const [ready, setReady] = useState(0);
  const [error, setError] = useState("");
  const initial = useRef(basemap);
  useEffect(() => { select.current = onSelect; selectPost.current = onSelectPost; }, [onSelect, onSelectPost]);

  useEffect(() => {
    if (!container.current || map.current) return;
    let disposed = false;
    let instance: MapLibreMap | null = null;
    void import("maplibre-gl").then((maplibregl) => {
      if (disposed || !container.current) return;
      maplibregl.setWorkerUrl(workerUrl);
      const m = new maplibregl.Map({ container: container.current, style: styleFor(initial.current), center: [20, 25], zoom: 1.6, minZoom: 1, maxZoom: 17, attributionControl: false, cooperativeGestures: true });
      instance = m; map.current = m;
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      m.on("error", () => { if (!m.isStyleLoaded()) setError("The basemap is unavailable. Posts and institutions remain available in the list view."); });
      const install = () => {
        setError("");
        const dark = initial.current === "dark";
        const ink = dark ? "#f3f5f8" : "#24354b", halo = dark ? "#0d1117" : "#ffffff";
        m.addSource(LINES, { type: "geojson", data: lineCollection([]) });
        m.addLayer({ id: "overlap-lines", type: "line", source: LINES, paint: { "line-color": "#8b68c8", "line-width": 1.4, "line-dasharray": [2, 2], "line-opacity": 0.8 } });
        m.addSource(FLOWS, { type: "geojson", data: flowCollection(null) });
        m.addLayer({ id: "post-flows", type: "line", source: FLOWS, paint: { "line-color": "#f5a623", "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["get", "posts"], 1, 1.2, 10, 4] } });
        m.addSource(TARGETS, { type: "geojson", data: targetCollection(null) });
        m.addLayer({ id: "target-rings", type: "circle", source: TARGETS, paint: { "circle-color": "rgba(224,60,60,.18)", "circle-stroke-color": "#e03c3c", "circle-stroke-width": 2,
          "circle-radius": ["interpolate", ["linear"], ["get", "posts"], 1, 14, 10, 30, 50, 46] } });
        m.addLayer({ id: "target-labels", type: "symbol", source: TARGETS, layout: { "text-field": ["concat", ["get", "name"], " · ", ["to-string", ["get", "posts"]]], "text-size": 11, "text-offset": [0, 2.2], "text-anchor": "top", "text-font": ["Noto Sans Bold"], "text-max-width": 10 },
          paint: { "text-color": ink, "text-halo-color": halo, "text-halo-width": 1.4 } });
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
          paint: { "text-color": ink, "text-halo-color": halo, "text-halo-width": 1.3 } });
        m.addSource(POSTS, { type: "geojson", data: postCollection(null), cluster: true, clusterMaxZoom: 9, clusterRadius: 34 });
        m.addLayer({ id: "post-clusters", type: "circle", source: POSTS, filter: ["has", "point_count"], paint: { "circle-color": "#f5c518", "circle-radius": ["step", ["get", "point_count"], 15, 10, 20, 50, 26], "circle-stroke-color": "#111", "circle-stroke-width": 2 } });
        m.addLayer({ id: "post-cluster-count", type: "symbol", source: POSTS, filter: ["has", "point_count"], layout: { "text-field": "{point_count_abbreviated}", "text-size": 12, "text-font": ["Noto Sans Bold"] }, paint: { "text-color": "#111" } });
        m.addLayer({ id: "post-pins", type: "circle", source: POSTS, filter: ["!", ["has", "point_count"]], paint: {
          "circle-color": ["case", ["==", ["get", "placement"], "origin"], "#f5c518", "rgba(245,197,24,.25)"], "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 6, 9, 10],
          "circle-stroke-color": ["case", ["get", "verified"], "#2bb673", "#f5c518"], "circle-stroke-width": ["case", ["get", "verified"], 3.5, 2] } });
        m.addLayer({ id: "post-selected", type: "circle", source: POSTS, filter: ["==", ["get", "id"], ""], paint: { "circle-radius": 15, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#4da3ff", "circle-stroke-width": 3 } });
        m.on("click", "post-pins", (event) => { const id = event.features?.[0]?.properties?.id; if (id) selectPost.current(String(id)); });
        for (const layer of ["points", "post-pins", "post-clusters", "clusters"]) {
          m.on("mouseenter", layer, () => { m.getCanvas().style.cursor = "pointer"; });
          m.on("mouseleave", layer, () => { m.getCanvas().style.cursor = ""; });
        }
        for (const [layer, source] of [["clusters", POINTS], ["post-clusters", POSTS]] as const) {
          m.on("click", layer, (event) => {
            const feature = event.features?.[0];
            if (!feature || feature.geometry.type !== "Point") return;
            const center = feature.geometry.coordinates as [number, number];
            void (m.getSource(source) as GeoJSONSource).getClusterExpansionZoom(Number(feature.properties?.cluster_id)).then((zoom) => m.easeTo({ center, zoom })).catch(() => undefined);
          });
        }
        m.on("click", "points", (event) => { const id = event.features?.[0]?.properties?.id; if (id) select.current(String(id)); });
        setReady((n) => n + 1);
      };
      m.on("style.load", () => { if (!m.getSource(POINTS)) install(); });
    }).catch(() => { if (!disposed) setError("The map could not start. Use the list view."); });
    return () => { disposed = true; instance?.remove(); map.current = null; };
  }, []);

  const applied = useRef(basemap);
  useEffect(() => {
    const m = map.current;
    if (!m || applied.current === basemap) return;
    applied.current = basemap; initial.current = basemap;
    m.setStyle(styleFor(basemap));
  }, [basemap]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !m.getSource(POINTS)) return;
    (m.getSource(POINTS) as GeoJSONSource).setData(pointCollection(rows, networks));
    (m.getSource(LINES) as GeoJSONSource).setData(lineCollection(lines));
    (m.getSource(POSTS) as GeoJSONSource).setData(postCollection(posts));
    (m.getSource(TARGETS) as GeoJSONSource).setData(targetCollection(posts));
    (m.getSource(FLOWS) as GeoJSONSource).setData(flowCollection(posts));
    const vis = (on: boolean) => (on ? "visible" : "none");
    const heat = mode === "heat";
    m.setLayoutProperty("heat", "visibility", vis(layers.institutions && heat));
    for (const layer of ["clusters", "cluster-count", "points", "labels", "overlap-lines"]) m.setLayoutProperty(layer, "visibility", vis(layers.institutions));
    for (const layer of ["post-pins", "post-clusters", "post-cluster-count", "post-selected"]) m.setLayoutProperty(layer, "visibility", vis(layers.posts));
    for (const layer of ["target-rings", "target-labels"]) m.setLayoutProperty(layer, "visibility", vis(layers.targets));
    m.setLayoutProperty("post-flows", "visibility", vis(layers.flows));
    m.setPaintProperty("points", "circle-opacity", heat ? 0.55 : 1);
  }, [rows, networks, lines, mode, ready, posts, layers]);

  useEffect(() => { if (ready && map.current?.getLayer("selected")) { map.current.setFilter("selected", ["==", ["get", "id"], selectedId || ""]); map.current.setFilter("post-selected", ["==", ["get", "id"], selectedPost || ""]); } }, [selectedId, selectedPost, ready]);

  const fitted = useRef("");
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const pts: Array<[number, number]> = [
      ...rows.filter((r) => r.placed && r.latitude !== null && r.longitude !== null).map((r) => [r.longitude as number, r.latitude as number] as [number, number]),
      ...(layers.targets ? (posts?.targets || []).map((t) => [t.longitude, t.latitude] as [number, number]) : []),
      ...(posts?.pins || []).filter((p) => p.latitude !== null && p.longitude !== null).map((p) => [p.longitude as number, p.latitude as number] as [number, number]),
    ];
    const key = String(pts.length) + pts.slice(0, 5).join(";");
    if (!pts.length || key === fitted.current) return;
    fitted.current = key;
    const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
    m.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 70, maxZoom: 6, duration: 400 });
  }, [rows, posts, ready, layers.targets]);

  return (
    <div className={`map-frame network-map ${basemap === "dark" ? "dark" : ""}`}>
      <div ref={container} className="map-canvas" role="application" aria-label="Map of posts and institutions. The list view has the same information." />
      {error && <div className="map-fallback"><span className="status-dot warn" />{error}</div>}
    </div>
  );
}
