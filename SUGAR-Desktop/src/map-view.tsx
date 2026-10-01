import { useEffect, useRef, useState } from "react";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import type { Institution } from "./types";

const SOURCE = "sugar-institutions";
type LayerKey = "active" | "proposed" | "closed" | "unknown";

function layerKey(status?: string): LayerKey {
  const value = (status || "unknown").toLowerCase();
  if (["active", "operational"].includes(value)) return "active";
  if (value === "proposed") return "proposed";
  if (["closed", "inactive"].includes(value)) return "closed";
  return "unknown";
}

export function institutionCoordinates(row: Institution): [number, number] | null {
  if (
    row.latitude === null || row.latitude === undefined || String(row.latitude).trim() === "" ||
    row.longitude === null || row.longitude === undefined || String(row.longitude).trim() === ""
  ) return null;
  const latitude = Number(row.latitude);
  const longitude = Number(row.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
  return [longitude, latitude];
}

function featureCollection(rows: Institution[], override?: { id: string; coordinates: [number, number] }): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: rows.flatMap((row) => {
      const point = override?.id === row.entity_id ? override.coordinates : institutionCoordinates(row);
      if (!point) return [];
      return [{
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: point },
        properties: {
          id: row.entity_id,
          name: row.name || "Unnamed institution",
          network: row.network || "Unclassified",
          status: (row.status || "unknown").toLowerCase(),
          city: row.city || "",
          country: row.country || "",
        },
      }];
    }),
  };
}

export function InstitutionMap({
  rows,
  onSelect,
  onMove,
}: {
  rows: Institution[];
  onSelect: (id: string) => void;
  onMove?: (id: string, latitude: number, longitude: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelect);
  const onMoveRef = useRef(onMove);
  const rowsRef = useRef(rows);
  const dragging = useRef<{ id: string; moved: boolean; startX: number; startY: number } | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [visibleLayers, setVisibleLayers] = useState<Record<LayerKey, boolean>>({ active: true, proposed: true, closed: true, unknown: true });
  const visibleRows = rows.filter((row) => visibleLayers[layerKey(row.status)]);
  const geojson = featureCollection(visibleRows);

  useEffect(() => { onSelectRef.current = onSelect; onMoveRef.current = onMove; rowsRef.current = rows; }, [onSelect, onMove, rows]);

  useEffect(() => {
    if (!container.current || map.current) return;
    let disposed = false;
    let instance: MapLibreMap | null = null;
    void import("maplibre-gl").then((maplibregl) => {
      if (disposed || !container.current) return;
      // MapLibre GL JS 6 needs Vite to bundle its worker explicitly. Without
      // this, the map shell loads but the worker fails and leaves a blank map.
      maplibregl.setWorkerUrl(workerUrl);
      const mapInstance = new maplibregl.Map({
        container: container.current,
        style: "https://tiles.openfreemap.org/styles/liberty",
        center: [-15, 20],
        zoom: 1.55,
        maxZoom: 18,
        minZoom: 1,
        attributionControl: false,
        cooperativeGestures: true,
      });
      instance = mapInstance;
      map.current = mapInstance;
      mapInstance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      mapInstance.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      mapInstance.on("error", (event) => {
        if (!mapInstance.isStyleLoaded()) setMapError("The basemap is unavailable. Institution locations remain available in the list.");
        console.warn("MapLibre map error", event.error?.message ?? event);
      });
      mapInstance.once("load", () => {
        setMapError("");
        mapInstance.addSource(SOURCE, {
          type: "geojson",
          data: featureCollection(rows),
          cluster: true,
          clusterMaxZoom: 13,
          clusterRadius: 48,
        });
        mapInstance.addLayer({
          id: "institution-clusters",
          type: "circle",
          source: SOURCE,
          filter: ["has", "point_count"],
          paint: {
            "circle-color": ["step", ["get", "point_count"], "#2f72d6", 20, "#7359c9", 60, "#da8747"],
            "circle-radius": ["step", ["get", "point_count"], 18, 20, 23, 60, 29],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
          },
        });
        mapInstance.addLayer({
          id: "institution-cluster-count",
          type: "symbol",
          source: SOURCE,
          filter: ["has", "point_count"],
          layout: { "text-field": "{point_count_abbreviated}", "text-size": 12, "text-font": ["Noto Sans Bold"] },
          paint: { "text-color": "#ffffff" },
        });
        mapInstance.addLayer({
          id: "institution-points",
          type: "circle",
          source: SOURCE,
          filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-color": [
              "match", ["get", "status"],
              "closed", "#929aa6", "inactive", "#929aa6", "proposed", "#8b68c8",
              "active", "#2e9a76", "operational", "#2e9a76", "#d29343",
            ],
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 4.5, 9, 7.5],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.6,
          },
        });
        mapInstance.addLayer({
          id: "institution-labels",
          type: "symbol",
          source: SOURCE,
          filter: ["!", ["has", "point_count"]],
          minzoom: 7.5,
          layout: {
            "text-field": ["get", "name"],
            "text-size": 11,
            "text-offset": [0, 1.2],
            "text-anchor": "top",
            "text-font": ["Noto Sans Regular"],
            "text-max-width": 16,
          },
          paint: { "text-color": "#24354b", "text-halo-color": "#ffffff", "text-halo-width": 1.3 },
        });
        mapInstance.on("click", "institution-clusters", (event) => {
          const point = event.features?.[0];
          const clusterId = point?.properties?.cluster_id;
          const source = mapInstance.getSource(SOURCE) as GeoJSONSource;
          if (!point?.geometry || point.geometry.type !== "Point") return;
          const center = point.geometry.coordinates as [number, number];
          void source.getClusterExpansionZoom(Number(clusterId)).then((zoom) => {
            mapInstance.easeTo({ center, zoom });
          }).catch((error: unknown) => console.warn("Could not expand institution cluster", error));
        });
        mapInstance.on("click", "institution-points", (event) => {
          const id = event.features?.[0]?.properties?.id;
          if (id) onSelectRef.current(String(id));
        });
        mapInstance.on("mousedown", "institution-points", (event) => {
          const id = event.features?.[0]?.properties?.id;
          if (!id || event.originalEvent.button !== 0) return;
          dragging.current = { id: String(id), moved: false, startX: event.point.x, startY: event.point.y };
          mapInstance.dragPan.disable();
          mapInstance.getCanvas().style.cursor = "grabbing";
          event.preventDefault();
        });
        mapInstance.on("mousemove", (event) => {
          const current = dragging.current;
          if (!current) return;
          if (Math.abs(event.point.x - current.startX) + Math.abs(event.point.y - current.startY) > 3) current.moved = true;
          if (!current.moved) return;
          const source = mapInstance.getSource(SOURCE) as GeoJSONSource;
          source.setData(featureCollection(rowsRef.current, { id: current.id, coordinates: [event.lngLat.lng, event.lngLat.lat] }));
        });
        const finishDrag = (event?: MapMouseEvent) => {
          const current = dragging.current;
          if (!current) return;
          dragging.current = null;
          mapInstance.dragPan.enable();
          mapInstance.getCanvas().style.cursor = "";
          if (current.moved && event && Number.isFinite(event.lngLat.lat) && Number.isFinite(event.lngLat.lng)) {
            onMoveRef.current?.(current.id, event.lngLat.lat, event.lngLat.lng);
          }
          if (!current.moved) return;
          const source = mapInstance.getSource(SOURCE) as GeoJSONSource;
          source.setData(featureCollection(rowsRef.current));
        };
        mapInstance.on("mouseup", finishDrag);
        mapInstance.on("mouseout", () => finishDrag());
        mapInstance.on("mouseenter", "institution-points", () => { mapInstance.getCanvas().style.cursor = "pointer"; });
        mapInstance.on("mouseleave", "institution-points", () => { if (!dragging.current) mapInstance.getCanvas().style.cursor = ""; });
        setMapReady(true);
      });
    }).catch((error: unknown) => {
      if (!disposed) setMapError(error instanceof Error ? "Map renderer could not start." : "Map renderer could not start.");
      console.error("Could not load MapLibre", error);
    });
    return () => {
      disposed = true;
      instance?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const source = mapReady ? map.current?.getSource(SOURCE) as GeoJSONSource | undefined : undefined;
    if (source) source.setData(geojson);
    if (!mapReady || !map.current) return;
    const located = rows.map((row) => institutionCoordinates(row)).filter((item): item is [number, number] => Boolean(item));
    if (!located.length) return;
    const longitudes = located.map(([longitude]) => longitude);
    const latitudes = located.map(([, latitude]) => latitude);
    map.current.fitBounds([
      [Math.min(...longitudes), Math.min(...latitudes)],
      [Math.max(...longitudes), Math.max(...latitudes)],
    ], { padding: 72, maxZoom: 5, duration: 450 });
  }, [visibleRows, mapReady]);

  return (
    <div className="map-frame">
      <div ref={container} className="map-canvas" />
      {mapError && <div className="map-fallback"><span className="status-dot warn" />{mapError}</div>}
      <div className="map-legend" aria-label="Map layers">
        {(["active", "proposed", "closed", "unknown"] as LayerKey[]).map((layer) => <label key={layer}><input type="checkbox" aria-label={`Map layer ${layer === "unknown" ? "Unverified" : titleCase(layer)}`} checked={visibleLayers[layer]} onChange={(event) => setVisibleLayers((current) => ({ ...current, [layer]: event.target.checked }))} /><i className={`legend-dot ${layer}`} />{layer === "unknown" ? "Unverified" : titleCase(layer)}</label>)}
      </div>
      <div className="map-count">{geojson.features.length} visible · drag a point to adjust its location · {rows.length - visibleRows.length} hidden by layers</div>
    </div>
  );
}

function titleCase(value: string): string { return value.replace(/^\w/, (letter) => letter.toUpperCase()); }
