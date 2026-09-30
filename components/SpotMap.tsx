"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import type { Coordinates } from "@/lib/types";

interface SpotMapProps {
  location: Coordinates;
  onLocationChange: (location: Coordinates) => void;
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

export default function SpotMap({ location, onLocationChange }: SpotMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const locationRef = useRef(location);
  const locationCallbackRef = useRef(onLocationChange);

  useEffect(() => { locationCallbackRef.current = onLocationChange; }, [onLocationChange]);
  useEffect(() => { locationRef.current = location; }, [location]);

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

    map.on("click", (event: maplibregl.MapMouseEvent) => {
      const latitude = Number(event.lngLat.lat.toFixed(5));
      const longitude = Number(event.lngLat.lng.toFixed(5));
      if (latitude < 30 || latitude > 38.5 || longitude < 7 || longitude > 12.5) return;
      marker.setLngLat([longitude, latitude]);
      locationCallbackRef.current({ latitude, longitude, name: "بقعة مختارة على الخريطة" });
    });

    mapRef.current = map;
    markerRef.current = marker;
    return () => {
      marker.remove();
      map.remove();
      markerRef.current = null;
      mapRef.current = null;
    };
    // The map is initialized once; prop synchronization is handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;
    locationRef.current = location;
    const target: [number, number] = [location.longitude, location.latitude];
    markerRef.current.setLngLat(target);
    mapRef.current.easeTo({ center: target, duration: 650 });
  }, [location]);

  return <div ref={containerRef} className="map-canvas" aria-label="خريطة لاختيار نقطة الوقوف على الساحل" />;
}
