import { useEffect, useState } from "react";

/**
 * Where the farmer is and what the weather is doing there, fetched once per
 * visit and shared by everything that shows it - the menu's "Your area" card
 * and the home screen's weather line. Before, the menu fetched it alone; with
 * the home screen showing it too, two fetches of the same forecast on a slow
 * connection would be one too many.
 *
 * Only fetched once the farmer has said yes to location - never by springing
 * the browser's permission dialog on page load. Where permission is not yet
 * given, `status` is "ask" and the menu offers a button that calls `locate`.
 */

let shared = { status: "idle", data: null, place: "", error: null };
const listeners = new Set();
let started = false;

function set(patch) {
  shared = { ...shared, ...patch };
  listeners.forEach((fn) => fn(shared));
}

async function fetchWeather(lat, lon) {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,rain_sum,showers_sum,precipitation_probability_mean&forecast_days=7&timezone=Asia%2FKolkata`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return response.json();
}

async function placeName(lat, lon) {
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`;
    const response = await fetch(url);
    if (!response.ok) return "";
    const data = await response.json();
    if (!data.address) return "";
    const { city, village, town, state_district, state } = data.address;
    // The district is the unit that matters: it is what a mandi price is
    // quoted for, and what the backend resolves a farm to.
    const place = village || town || city || state_district || data.display_name.split(",")[0];
    return [place, state].filter(Boolean).join(", ");
  } catch (e) {
    return "";
  }
}

/** Ask for the position (the farmer's tap is their yes) and fetch for it. */
export function locate() {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    set({ status: "error", error: "Geolocation is not supported by your browser." });
    return;
  }
  set({ status: "loading", error: null });
  navigator.geolocation.getCurrentPosition(
    async ({ coords }) => {
      try {
        const [data, place] = await Promise.all([
          fetchWeather(coords.latitude, coords.longitude),
          placeName(coords.latitude, coords.longitude),
        ]);
        set({ status: "ready", data, place });
      } catch (e) {
        console.error("Failed to fetch weather data:", e);
        set({ status: "error", error: "Could not fetch weather data." });
      }
    },
    (err) => {
      console.error("Geolocation error:", err);
      set({ status: "error", error: "Location permission denied or unavailable." });
    }
  );
}

async function start() {
  if (started) return;
  started = true;
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    set({ status: "error", error: "Geolocation is not supported by your browser." });
    return;
  }
  try {
    const status = await navigator.permissions?.query({ name: "geolocation" });
    if (status && status.state === "granted") {
      locate();
      return;
    }
  } catch (e) {
    /* no Permissions API: ask on a tap rather than guess */
  }
  set({ status: "ask" });
}

/** The shared area weather: { status, data, place, error, locate }. */
export function useAreaWeather() {
  const [state, setState] = useState(shared);
  useEffect(() => {
    listeners.add(setState);
    setState(shared);
    start();
    return () => listeners.delete(setState);
  }, []);
  return { ...state, locate };
}

/** The first day in the forecast carrying meaningful rain, if there is one. */
export function nextWetDay(daily) {
  if (!daily || !daily.rain_sum || !daily.time) return null;
  for (let i = 0; i < daily.rain_sum.length; i += 1) {
    // Below a millimetre is dew and rounding, not something to plan around.
    if (daily.rain_sum[i] >= 1) {
      return { date: new Date(daily.time[i]), mm: daily.rain_sum[i], index: i };
    }
  }
  return null;
}

export function describeDay(date, index) {
  if (index === 0) return "today";
  if (index === 1) return "tomorrow";
  return date.toLocaleDateString("en-IN", { weekday: "long" });
}
