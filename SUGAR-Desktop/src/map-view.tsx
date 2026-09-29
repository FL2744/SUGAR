import { useEffect, useRef, useState } from "react";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import type { Institution } from "./types";

const SOURCE = "sugar-institutions";

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

function featureCollection(rows: Institution[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: rows.flatMap((row) => {
      const point = institutionCoordinates(row);
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
}: {
  rows: Institution[];
  onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelect);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const geojson = featureCollection(rows);

  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

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
        mapInstance.on("mouseenter", "institution-points", () => { mapInstance.getCanvas().style.cursor = "pointer"; });
        mapInstance.on("mouseleave", "institution-points", () => { mapInstance.getCanvas().style.cursor = ""; });
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
  }, [rows, mapReady]);

  return (
    <div className="map-frame">
      <div ref={container} className="map-canvas" />
      {mapError && <div className="map-fallback"><span className="status-dot warn" />{mapError}</div>}
      <div className="map-legend">
        <span><i className="legend-dot active" />Active</span>
        <span><i className="legend-dot proposed" />Proposed</span>
        <span><i className="legend-dot closed" />Closed</span>
        <span><i className="legend-dot unknown" />Unverified</span>
      </div>
      <div className="map-count">{geojson.features.length} mapped · {rows.length - geojson.features.length} without coordinates</div>
    </div>
  );
}
