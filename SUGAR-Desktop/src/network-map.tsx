import { useCallback, useEffect, useRef, useState } from "react";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import type { Institution, NetworkRow, PostMap } from "./research-types";
import { publicationTime, type PostStyle } from "./map-data";

const POINTS = "sugar-network-points";
const LINES = "sugar-network-lines";
const POSTS = "sugar-post-pins";
const TARGETS = "sugar-post-targets";
const FLOWS = "sugar-post-flows";
const POST_HEAT = "sugar-post-heat";
const INSTITUTION_HEAT = "sugar-institution-heat";

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
const postCollection = (posts: PostMap | null, timeDomain?: [number, number]) => ({
  type: "FeatureCollection" as const,
  features: (posts?.pins || []).filter((p) => p.latitude !== null && p.longitude !== null).map((p) => ({
    type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [p.longitude as number, p.latitude as number] },
    properties: { id: p.item_id, placement: p.placement, verified: p.verified,
      recency: publicationTime(p) === null ? 0 : Math.max(0, Math.min(1, ((publicationTime(p) || 0) - (timeDomain?.[0] || 0)) / Math.max(1, (timeDomain?.[1] || Date.now()) - (timeDomain?.[0] || 0)))),
      time_n: publicationTime(p) === null ? 0 : 1,
      valence: p.sentiment?.valence ?? 0, valence_n: p.sentiment?.valence == null ? 0 : 1,
      intensity: p.sentiment?.intensity ?? 0, intensity_n: p.sentiment?.intensity == null ? 0 : 1,
      direction: p.sentiment?.direction ?? 0, direction_n: p.sentiment?.direction == null ? 0 : 1 },
  })),
});
const targetCollection = (posts: PostMap | null) => ({ type: "FeatureCollection" as const, features: (posts?.targets || []).map((t) => ({ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [t.longitude, t.latitude] }, properties: { name: t.name, posts: t.posts } })) });
/** A gentle curve between two points (a quadratic bezier bowed away from the straight line) so lines read as arcs, not ruler marks. */
function arc(from: [number, number], to: [number, number], steps = 36): Array<[number, number]> {
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const bow = Math.min(0.28, 0.12 + Math.hypot(dx, dy) / 400);
  const control: [number, number] = [(from[0] + to[0]) / 2 - dy * bow, (from[1] + to[1]) / 2 + dx * bow];
  return Array.from({ length: steps + 1 }, (_, i) => {
    const t = i / steps, u = 1 - t;
    return [u * u * from[0] + 2 * u * t * control[0] + t * t * to[0], u * u * from[1] + 2 * u * t * control[1] + t * t * to[1]] as [number, number];
  });
}
const flowCollection = (posts: PostMap | null) => ({ type: "FeatureCollection" as const, features: (posts?.flows || []).map((f) => ({ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: arc(f.from, f.to) }, properties: { posts: f.posts } })) });
const reduceMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function postColor(style: PostStyle, cluster: boolean): ExpressionSpecification | string {
  if (style === "points" || style === "density") return cluster ? "#f5c518" : ["case", ["==", ["get", "placement"], "origin"], "#f5c518", "rgba(245,197,24,.25)"];
  const axis = style === "recency" ? "recency" : style;
  const n = style === "recency" ? "time_n" : `${axis}_n`;
  const value: ExpressionSpecification = cluster ? style === "recency" ? ["get", "time_max"] : ["/", ["get", `${axis}_sum`], ["max", 1, ["get", n]]] : ["get", axis];
  const ramp: ExpressionSpecification = style === "recency" ? ["interpolate", ["linear"], value, 0, "#2b83ba", .5, "#f0db87", 1, "#d84b32"]
    : style === "intensity" ? ["interpolate", ["linear"], value, 0, "#e3d6ee", .5, "#9b65ad", 1, "#6d1f80"]
      : ["interpolate", ["linear"], value, -1, style === "valence" ? "#c55235" : "#2b83ba", 0, "#d7dce1", 1, style === "valence" ? "#16977a" : "#d9822b"];
  return ["case", [">", ["get", n], 0], ramp, "#87929f"];
}

/** Posts, institutions and targets on one map. Posts: yellow = posted from here, hollow = a place the text names (approximate). Targets: rings by country. */
export function NetworkMap({ rows, networks, mode, lines, selectedId, onSelect, basemap, posts, layers, selectedPost, onSelectPost, selectedTarget, onSelectTarget, postStyle = "points", timeDomain }: {
  rows: Institution[]; networks: NetworkRow[]; mode: MapMode; lines: Line[]; selectedId: string; onSelect: (id: string) => void; basemap: Basemap;
  posts: PostMap | null; layers: PostLayers; selectedPost: string; onSelectPost: (id: string) => void; selectedTarget: string; onSelectTarget: (name: string) => void;
  postStyle?: PostStyle; timeDomain?: [number, number];
}) {
  const container = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const map = useRef<MapLibreMap | null>(null);
  const select = useRef(onSelect);
  const selectPost = useRef(onSelectPost);
  const selectTarget = useRef(onSelectTarget);
  const [ready, setReady] = useState(0);
  const [error, setError] = useState("");
  const initial = useRef(basemap);
  useEffect(() => { select.current = onSelect; selectPost.current = onSelectPost; selectTarget.current = onSelectTarget; }, [onSelect, onSelectPost, onSelectTarget]);

  useEffect(() => {
    if (!container.current || map.current) return;
    let disposed = false;
    let instance: MapLibreMap | null = null;
    void import("maplibre-gl").then((maplibregl) => {
      if (disposed || !container.current) return;
      maplibregl.setWorkerUrl(workerUrl);
      const m = new maplibregl.Map({ container: container.current, style: styleFor(initial.current), center: [20, 25], zoom: 1.6, minZoom: 1, maxZoom: 17, attributionControl: false, cooperativeGestures: true });
      let eventsBound = false;
      instance = m; map.current = m;
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      m.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");
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
        m.addSource(INSTITUTION_HEAT, { type: "geojson", data: pointCollection([], []) });
        m.addLayer({ id: "heat", type: "heatmap", source: INSTITUTION_HEAT, filter: ["==", ["get", "role"], "subject"], layout: { visibility: "none" },
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
        m.addSource(POST_HEAT, { type: "geojson", data: postCollection(null) });
        m.addLayer({ id: "post-density", type: "heatmap", source: POST_HEAT, filter: ["==", ["get", "placement"], "origin"], layout: { visibility: "none" },
          paint: { "heatmap-weight": 1, "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 1, .7, 10, 1.6],
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 1, 15, 10, 45], "heatmap-opacity": .8,
            "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", .2, "#2b83ba", .5, "#f0db87", .8, "#ef8a45", 1, "#b9382c"] } });
        m.addSource(POSTS, { type: "geojson", data: postCollection(null), cluster: true, clusterMaxZoom: 9, clusterRadius: 34,
          clusterProperties: { time_max: ["max", ["get", "recency"]], time_n: ["+", ["get", "time_n"]],
            valence_sum: ["+", ["get", "valence"]], valence_n: ["+", ["get", "valence_n"]],
            intensity_sum: ["+", ["get", "intensity"]], intensity_n: ["+", ["get", "intensity_n"]],
            direction_sum: ["+", ["get", "direction"]], direction_n: ["+", ["get", "direction_n"]] } });
        m.addLayer({ id: "post-clusters", type: "circle", source: POSTS, filter: ["has", "point_count"], paint: { "circle-color": "#f5c518", "circle-radius": ["step", ["get", "point_count"], 15, 10, 20, 50, 26], "circle-stroke-color": "#111", "circle-stroke-width": 2 } });
        m.addLayer({ id: "post-cluster-count", type: "symbol", source: POSTS, filter: ["has", "point_count"], layout: { "text-field": "{point_count_abbreviated}", "text-size": 12, "text-font": ["Noto Sans Bold"] }, paint: { "text-color": "#111" } });
        m.addLayer({ id: "post-glow", type: "circle", source: POSTS, filter: ["!", ["has", "point_count"]], paint: { "circle-color": "#f5c518", "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 14, 9, 24], "circle-blur": 1, "circle-opacity": 0.35 } });
        m.addLayer({ id: "post-pins", type: "circle", source: POSTS, filter: ["!", ["has", "point_count"]], paint: {
          "circle-color": ["case", ["==", ["get", "placement"], "origin"], "#f5c518", "rgba(245,197,24,.25)"], "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 6, 9, 10],
          "circle-stroke-color": ["case", ["get", "verified"], "#2bb673", "#f5c518"], "circle-stroke-width": ["case", ["get", "verified"], 3.5, 2] } });
        m.addLayer({ id: "post-selected", type: "circle", source: POSTS, filter: ["==", ["get", "id"], ""], paint: { "circle-radius": 15, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#4da3ff", "circle-stroke-width": 3 } });
        m.addLayer({ id: "target-selected", type: "circle", source: TARGETS, filter: ["==", ["get", "name"], ""], paint: { "circle-radius": ["interpolate", ["linear"], ["get", "posts"], 1, 20, 50, 52], "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#4da3ff", "circle-stroke-width": 3 } });
        if (!eventsBound) {
        eventsBound = true;
        m.on("click", "target-rings", (event) => { const name = event.features?.[0]?.properties?.name; if (name) selectTarget.current(String(name)); });
        m.on("click", "post-pins", (event) => { const id = event.features?.[0]?.properties?.id; if (id) selectPost.current(String(id)); });
        for (const layer of ["points", "post-pins", "post-clusters", "clusters", "target-rings"]) {
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
        }
        setReady((n) => n + 1);
      };
      m.on("style.load", () => { if (!m.getSource(POINTS)) install(); });
    }).catch(() => { if (!disposed) setError("The map could not start. Use the list view."); });
    return () => { disposed = true; instance?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(() => map.current?.resize());
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); setExpanded(false); }
      if (e.key === "Tab") {
        const controls = Array.from(frame.current?.querySelectorAll<HTMLElement>("button, a[href], [tabindex='0']") || []).filter((el) => el.offsetParent !== null);
        const first = controls[0], last = controls[controls.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    frame.current?.focus();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); previous?.focus(); };
  }, [expanded]);

  const applied = useRef(basemap);
  useEffect(() => {
    initial.current = basemap;
    const m = map.current;
    if (!m) { applied.current = basemap; return; }
    if (applied.current === basemap) return;
    applied.current = basemap;
    m.setStyle(styleFor(basemap));
  }, [basemap]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !m.getLayer("post-pins")) return;
    (m.getSource(POINTS) as GeoJSONSource).setData(pointCollection(rows, networks));
    (m.getSource(INSTITUTION_HEAT) as GeoJSONSource).setData(pointCollection(rows, networks));
    (m.getSource(LINES) as GeoJSONSource).setData(lineCollection(lines));
    (m.getSource(POSTS) as GeoJSONSource).setData(postCollection(posts, timeDomain));
    (m.getSource(POST_HEAT) as GeoJSONSource).setData(postCollection(posts, timeDomain));
    (m.getSource(TARGETS) as GeoJSONSource).setData(targetCollection(posts));
    (m.getSource(FLOWS) as GeoJSONSource).setData(flowCollection(posts));
    const vis = (on: boolean) => (on ? "visible" : "none");
    const heat = mode === "heat";
    m.setLayoutProperty("heat", "visibility", vis(layers.institutions && heat));
    for (const layer of ["clusters", "cluster-count", "points", "labels", "overlap-lines"]) m.setLayoutProperty(layer, "visibility", vis(layers.institutions));
    for (const layer of ["post-glow", "post-pins", "post-clusters", "post-cluster-count", "post-selected"]) m.setLayoutProperty(layer, "visibility", vis(layers.posts));
    m.setLayoutProperty("post-density", "visibility", vis(layers.posts && postStyle === "density"));
    m.setLayoutProperty("post-glow", "visibility", vis(layers.posts && postStyle === "points"));
    for (const layer of ["target-rings", "target-labels", "target-selected"]) m.setLayoutProperty(layer, "visibility", vis(layers.targets));
    m.setLayoutProperty("post-flows", "visibility", vis(layers.flows));
    m.setPaintProperty("points", "circle-opacity", heat ? 0.55 : 1);
    m.setLayoutProperty("selected", "visibility", vis(layers.institutions));
    m.setPaintProperty("post-pins", "circle-color", postColor(postStyle, false));
    m.setPaintProperty("post-clusters", "circle-color", postColor(postStyle, true));
    m.setPaintProperty("post-pins", "circle-opacity", postStyle === "density" ? .5 : 1);
  }, [rows, networks, lines, mode, ready, posts, layers, postStyle, timeDomain]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m?.getLayer("target-selected")) return;
    m.setFilter("target-selected", ["==", ["get", "name"], selectedTarget || ""]);
    const t = posts?.targets.find((x) => x.name === selectedTarget);
    if (t) m.flyTo({ center: [t.longitude, t.latitude], zoom: Math.max(m.getZoom(), 3.2), duration: reduceMotion() ? 0 : 900 });
  }, [selectedTarget, ready, posts]);
  useEffect(() => {
    const m = map.current;
    const pin = posts?.pins.find((p) => p.item_id === selectedPost);
    if (ready && m && pin && pin.latitude !== null && pin.longitude !== null) m.flyTo({ center: [pin.longitude, pin.latitude], zoom: Math.max(m.getZoom(), 4), duration: reduceMotion() ? 0 : 700 });
  }, [selectedPost, ready, posts]);

  // Motion: marching dashes along the arcs and a slow pulse on target rings. Off when the system asks for reduced motion.
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || reduceMotion()) return;
    const frames: Array<number[]> = [[0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5]];
    let i = 0, alive = true;
    const timer = window.setInterval(() => {
      if (!alive || !m.getLayer("post-flows") || m.getLayoutProperty("post-flows", "visibility") === "none") return;
      i = (i + 1) % frames.length;
      m.setPaintProperty("post-flows", "line-dasharray", frames[i]);
      const wave = 0.5 + 0.5 * Math.sin(Date.now() / 450);
      if (m.getLayer("target-rings")) { m.setPaintProperty("target-rings", "circle-stroke-opacity", 0.55 + 0.45 * wave); m.setPaintProperty("target-rings", "circle-opacity", 0.55 + 0.45 * wave); }
    }, 90);
    return () => { alive = false; window.clearInterval(timer); };
  }, [ready]);

  useEffect(() => { if (ready && map.current?.getLayer("selected")) { map.current.setFilter("selected", ["==", ["get", "id"], selectedId || ""]); map.current.setFilter("post-selected", ["==", ["get", "id"], selectedPost || ""]); } }, [selectedId, selectedPost, ready]);

  const fitData = useCallback(() => {
    const m = map.current;
    if (!ready || !m) return;
    const pts: Array<[number, number]> = [
      ...(layers.institutions ? rows.filter((r) => r.placed && r.latitude !== null && r.longitude !== null).map((r) => [r.longitude as number, r.latitude as number] as [number, number]) : []),
      ...(layers.targets ? (posts?.targets || []).map((t) => [t.longitude, t.latitude] as [number, number]) : []),
      ...(layers.posts ? (posts?.pins || []).filter((p) => p.latitude !== null && p.longitude !== null).map((p) => [p.longitude as number, p.latitude as number] as [number, number]) : []),
    ];
    if (!pts.length) return;
    let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
    for (const [lon, lat] of pts) { west = Math.min(west, lon); east = Math.max(east, lon); south = Math.min(south, lat); north = Math.max(north, lat); }
    m.fitBounds([[west, south], [east, north]], { padding: 60, maxZoom: 6, duration: reduceMotion() ? 0 : 400 });
  }, [rows, posts, ready, layers]);
  const fitted = useRef(false);
  useEffect(() => { if (!fitted.current && ready && (rows.some((r) => r.placed) || posts?.pins.length)) { fitData(); fitted.current = true; } }, [fitData, rows, posts, ready]);

  return (
    <div ref={frame} tabIndex={-1} role={expanded ? "dialog" : undefined} aria-modal={expanded || undefined} aria-label={expanded ? "Expanded research map" : undefined} className={`map-frame network-map ${basemap === "dark" ? "dark" : ""} ${expanded ? "is-expanded" : ""}`}>
      <div className="map-canvas-actions"><button className="button button-secondary button-small" onClick={fitData} disabled={!ready}>Fit visible data</button><button className="button button-secondary button-small" onClick={() => setExpanded(!expanded)} aria-pressed={expanded}>{expanded ? "Return to layout" : "Expand map"}</button></div>
      <div className="map-legend-lite" aria-hidden="true">
        <span><i className="lg lg-origin" /> Posted from</span><span><i className="lg lg-mention" /> Place named</span><span><i className="lg lg-target" /> Target</span><span><i className="lg lg-inst" /> Institution</span>
      </div>
      {postStyle !== "points" && <div className={`map-color-legend ${postStyle}`} aria-label="Post color legend"><strong>{postStyle === "density" ? "Origin density" : postStyle === "recency" ? "Publication time" : postStyle === "valence" ? "Negative → positive language" : postStyle === "intensity" ? "Lower → higher intensity" : "Inward → outward language"}</strong><i />
        <small>{postStyle === "density" ? "Recorded origins only · relative density at this zoom" : postStyle === "recency" ? "Older → newer · clusters use latest date" : "Clusters average scored items · gray = unscored"}</small></div>}
      <div ref={container} className="map-canvas" role="application" aria-label="Map of posts and institutions. The list view has the same information." />
      {error && <div className="map-fallback"><span className="status-dot warn" />{error}</div>}
    </div>
  );
}
