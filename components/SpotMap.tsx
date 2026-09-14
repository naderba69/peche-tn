"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  GeoJSONSourceSpecification,
  Map as MapLibreMap,
  Marker,
} from "maplibre-gl";
import type { Coordinates } from "@/lib/types";

type MapMode = "spot" | "seaward";

interface SpotMapProps {
  location: Coordinates;
  orientationDeg: number;
  mode: MapMode;
  onLocationChange: (location: Coordinates) => void;
  onOrientationChange: (degrees: number) => void;
}

const mapStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#092126" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -0.55, "raster-brightness-max": 0.72, "raster-contrast": 0.14 } },
  ],
};

function degreesToRadians(value: number): number {
  return value * Math.PI / 180;
}

function radiansToDegrees(value: number): number {
  return value * 180 / Math.PI;
}

function initialBearing(from: Coordinates, longitude: number, latitude: number): number | null {
  const fromLatitude = degreesToRadians(from.latitude);
  const toLatitude = degreesToRadians(latitude);
  const longitudeDelta = degreesToRadians(longitude - from.longitude);
  const y = Math.sin(longitudeDelta) * Math.cos(toLatitude);
  const x = Math.cos(fromLatitude) * Math.sin(toLatitude)
    - Math.sin(fromLatitude) * Math.cos(toLatitude) * Math.cos(longitudeDelta);
  if (Math.abs(x) < 1e-12 && Math.abs(y) < 1e-12) return null;
  return (radiansToDegrees(Math.atan2(y, x)) + 360) % 360;
}

function destination(
  from: Coordinates,
  bearingDeg: number,
  distanceKm: number,
): [number, number] {
  const angularDistance = distanceKm / 6371.0088;
  const bearing = degreesToRadians(bearingDeg);
  const latitude = degreesToRadians(from.latitude);
  const longitude = degreesToRadians(from.longitude);
  const destinationLatitude = Math.asin(
    Math.sin(latitude) * Math.cos(angularDistance)
      + Math.cos(latitude) * Math.sin(angularDistance) * Math.cos(bearing),
  );
  const destinationLongitude = longitude + Math.atan2(
    Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latitude),
    Math.cos(angularDistance) - Math.sin(latitude) * Math.sin(destinationLatitude),
  );
  return [
    ((radiansToDegrees(destinationLongitude) + 540) % 360) - 180,
    radiansToDegrees(destinationLatitude),
  ];
}

function visualBearingDistanceKm(zoom: number): number {
  return Math.max(0.25, Math.min(18, 18 / 2 ** (zoom - 8.7)));
}

function bearingFeature(
  location: Coordinates,
  orientationDeg: number,
  distanceKm: number,
): GeoJSONSourceSpecification["data"] {
  const end = destination(location, orientationDeg, distanceKm);
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: [[location.longitude, location.latitude], end],
        },
      },
      {
        type: "Feature",
        properties: {},
        geometry: { type: "Point", coordinates: end },
      },
    ],
  };
}

export default function SpotMap({
  location,
  orientationDeg,
  mode,
  onLocationChange,
  onOrientationChange,
}: SpotMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const bearingMarkerRef = useRef<Marker | null>(null);
  const locationRef = useRef(location);
  const orientationRef = useRef(orientationDeg);
  const modeRef = useRef<MapMode>(mode);
  const locationCallbackRef = useRef(onLocationChange);
  const orientationCallbackRef = useRef(onOrientationChange);

  useEffect(() => { locationCallbackRef.current = onLocationChange; }, [onLocationChange]);
  useEffect(() => { orientationCallbackRef.current = onOrientationChange; }, [onOrientationChange]);
  useEffect(() => { locationRef.current = location; }, [location]);
  useEffect(() => { orientationRef.current = orientationDeg; }, [orientationDeg]);
  useEffect(() => {
    modeRef.current = mode;
    if (mapRef.current) mapRef.current.getCanvas().style.cursor = "crosshair";
  }, [mode]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: mapStyle,
      center: [location.longitude, location.latitude],
      zoom: 8.7,
      minZoom: 6,
      maxZoom: 17,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
    map.getCanvas().style.cursor = "crosshair";

    const marker = new maplibregl.Marker({ color: "#42e8c4" })
      .setLngLat([location.longitude, location.latitude])
      .addTo(map);
    const bearingElement = document.createElement("div");
    bearingElement.className = "seaward-map-target";
    bearingElement.setAttribute("aria-hidden", "true");
    bearingElement.textContent = "◉";
    const bearingMarker = new maplibregl.Marker({ element: bearingElement, anchor: "center" })
      .setLngLat(destination(location, orientationDeg, 18))
      .addTo(map);

    const updateBearingLine = () => {
      const source = map.getSource("seaward-bearing") as GeoJSONSource | undefined;
      if (!source) return;
      const visualDistanceKm = visualBearingDistanceKm(map.getZoom());
      source.setData(bearingFeature(locationRef.current, orientationRef.current, visualDistanceKm));
      bearingMarker.setLngLat(
        destination(locationRef.current, orientationRef.current, visualDistanceKm),
      );
    };

    map.on("load", () => {
      map.addSource("seaward-bearing", {
        type: "geojson",
        data: bearingFeature(locationRef.current, orientationRef.current, 18),
      });
      map.addLayer({
        id: "seaward-bearing-line",
        type: "line",
        source: "seaward-bearing",
        paint: {
          "line-color": "#00d9ff",
          "line-width": 4,
          "line-opacity": 0.9,
          "line-dasharray": [1.5, 1],
        },
      });
      map.addLayer({
        id: "seaward-bearing-end",
        type: "circle",
        source: "seaward-bearing",
        paint: {
          "circle-color": "#00d9ff",
          "circle-radius": 6,
          "circle-stroke-color": "#062326",
          "circle-stroke-width": 2,
        },
        filter: ["==", ["geometry-type"], "Point"],
      });
      updateBearingLine();
    });
    map.on("zoomend", updateBearingLine);

    map.on("click", (event: maplibregl.MapMouseEvent) => {
      const latitude = Number(event.lngLat.lat.toFixed(5));
      const longitude = Number(event.lngLat.lng.toFixed(5));
      if (modeRef.current === "seaward") {
        const bearing = initialBearing(locationRef.current, longitude, latitude);
        if (bearing !== null) orientationCallbackRef.current(bearing);
        return;
      }
      if (latitude < 30 || latitude > 38.5 || longitude < 7 || longitude > 12.5) return;
      marker.setLngLat([longitude, latitude]);
      locationCallbackRef.current({ latitude, longitude, name: "بقعة مختارة على الخريطة" });
    });
    mapRef.current = map;
    markerRef.current = marker;
    bearingMarkerRef.current = bearingMarker;
    return () => {
      marker.remove();
      bearingMarker.remove();
      map.remove();
      markerRef.current = null;
      bearingMarkerRef.current = null;
      mapRef.current = null;
    };
    // The map is initialized once; prop synchronization is handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!mapRef.current || !markerRef.current || !bearingMarkerRef.current) return;
    locationRef.current = location;
    orientationRef.current = orientationDeg;
    const target: [number, number] = [location.longitude, location.latitude];
    markerRef.current.setLngLat(target);
    mapRef.current.easeTo({ center: target, duration: 650 });
    const source = mapRef.current.getSource("seaward-bearing") as GeoJSONSource | undefined;
    if (source) {
      const visualDistanceKm = visualBearingDistanceKm(mapRef.current.getZoom());
      source.setData(bearingFeature(location, orientationDeg, visualDistanceKm));
      bearingMarkerRef.current.setLngLat(destination(location, orientationDeg, visualDistanceKm));
    }
  }, [location, orientationDeg]);

  const label = mode === "spot"
    ? "خريطة لاختيار نقطة الوقوف على الساحل"
    : "خريطة لاختيار نقطة داخل البحر وحساب اتجاه البحر";
  return <div ref={containerRef} className="map-canvas" aria-label={label} />;
}
