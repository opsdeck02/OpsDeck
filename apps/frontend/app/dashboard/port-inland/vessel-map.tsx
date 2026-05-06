"use client";

import L from "leaflet";
import { useEffect } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

type VesselMapProps = {
  vesselName: string;
  latitude: number;
  longitude: number;
  speedKnots: number;
  headingDegrees: number;
  timestamp: string;
  source: string;
  isMock: boolean;
};

const markerIcon = L.divIcon({
  className: "",
  html: '<div class="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-primary text-primaryForeground shadow-lg">▲</div>',
  iconSize: [32, 32],
  iconAnchor: [16, 16],
  popupAnchor: [0, -16],
});

export default function VesselMap({
  vesselName,
  latitude,
  longitude,
  speedKnots,
  headingDegrees,
  timestamp,
  source,
  isMock,
}: VesselMapProps) {
  const center: [number, number] = [latitude, longitude];

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border">
      <MapContainer
        center={center}
        zoom={5}
        scrollWheelZoom={false}
        className="h-[280px] w-full"
      >
        <MapRecenter center={center} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={center} icon={markerIcon}>
          <Popup>
            <div className="grid gap-1 text-sm">
              <strong>{vesselName}</strong>
              <span>Speed: {speedKnots.toFixed(1)} kn</span>
              <span>Heading: {headingDegrees.toFixed(0)} deg</span>
              <span>Last update: {formatDate(timestamp)}</span>
              <span>Source: {isMock ? "Mock AIS" : source}</span>
              {isMock ? <span>Demo vessel position, not live AIS.</span> : null}
            </div>
          </Popup>
        </Marker>
      </MapContainer>
    </div>
  );
}

function MapRecenter({ center }: { center: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, map.getZoom(), { animate: false });
  }, [center, map]);
  return null;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
