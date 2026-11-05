import React, { useState, useContext, useEffect } from "react";
import { IoIosMenu } from "react-icons/io";
import { FaRightFromBracket } from "react-icons/fa6";
import { Context } from "../../Context/ContextProvider";
import { Auth } from "../../Context/AuthProvider";

/**
 * Where the farmer is, and what the sky is going to do about it.
 *
 * This panel used to print the farmer's own latitude and longitude to five
 * decimal places - roughly one-metre precision, which tells a farmer standing
 * in the field nothing they do not already know - followed by seven lines
 * reading "Day 1: 0.0 mm". That is a debug view of an API response, not a
 * weather widget.
 *
 * What replaces it is the two facts a farmer actually acts on: where the system
 * thinks they are, so a wrong district is visible and can be corrected in the
 * question, and when it is next going to rain.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO. It does not say "do not spray before
 * Thursday", however much that sentence wants to be written here. Spray timing
 * depends on the chemical, the crop, the pest and the rain, and the agent
 * answers that from the statutory register with all four in hand. A weather
 * widget that hands out agronomic advice from a single rainfall number is the
 * interface claiming more than the system behind it knows. It reports the rain.
 * The farmer asks the question.
 */

/** The first day in the forecast carrying meaningful rain, if there is one. */
function nextWetDay(daily) {
  if (!daily || !daily.rain_sum || !daily.time) return null;
  for (let i = 0; i < daily.rain_sum.length; i += 1) {
    // Below a millimetre is dew and rounding, not something to plan around.
    if (daily.rain_sum[i] >= 1) {
      return { date: new Date(daily.time[i]), mm: daily.rain_sum[i], index: i };
    }
  }
  return null;
}

function describeDay(date, index) {
  if (index === 0) return "today";
  if (index === 1) return "tomorrow";
  return date.toLocaleDateString("en-IN", { weekday: "long" });
}

const svg = (paths) => (
  <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {paths}
  </svg>
);
const ICONS = {
  home: svg(<><path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" /></>),
  plus: svg(<><path d="M12 5v14" /><path d="M5 12h14" /></>),
  compass: svg(<><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5l-2 5-5 2 2-5z" /></>),
  news: svg(<><path d="M4 5h13v14H6a2 2 0 0 1-2-2z" /><path d="M17 9h3v8a2 2 0 0 1-2 2" /><path d="M8 9h5" /><path d="M8 13h5" /></>),
};

function Sidebar() {
  // Open by default on a wide screen, where it is a panel; closed on a phone,
  // where it is a drawer over the chat.
  const [extended, setExtended] = useState(
    () => typeof window !== "undefined" && window.innerWidth >= 1024
  );
  const { newChat, goHome, setScreen, screen, chats = [], openChat, currentChatId } = useContext(Context);
  const { user, signOut } = useContext(Auth);

  const [weatherData, setWeatherData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [locationName, setLocationName] = useState("");
  // Weather is only fetched once the farmer has said yes to location - never
  // by springing the browser's permission dialog on page load, which on a
  // phone (where this panel is hidden) arrived with no explanation at all.
  const [askToLocate, setAskToLocate] = useState(false);
  const [locateTick, setLocateTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const fetchWeather = async (lat, lon) => {
      try {
        const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,rain_sum,showers_sum,precipitation_probability_mean&forecast_days=7&timezone=Asia%2FKolkata`;

        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setWeatherData(data);
        setLoading(false);
      } catch (e) {
        setError("Could not fetch weather data.");
        setLoading(false);
        console.error("Failed to fetch weather data:", e);
      }
    };

    const getReverseGeocode = async (lat, lon) => {
      try {
        const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`;
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (data.address) {
          const { city, village, town, state_district, state } = data.address;
          // The district is the unit that matters: it is what a mandi price is
          // quoted for, and what the backend resolves a farm to.
          const place =
            village || town || city || state_district || data.display_name.split(",")[0];
          setLocationName([place, state].filter(Boolean).join(", "));
        } else {
          setLocationName("");
        }
      } catch (e) {
        console.error("Failed to get location name:", e);
        setLocationName("");
      }
    };

    const locate = () => navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          fetchWeather(latitude, longitude);
          getReverseGeocode(latitude, longitude);
        },
        (err) => {
          setError("Location permission denied or unavailable.");
          setLoading(false);
          console.error("Geolocation error:", err);
        }
      );

    if (!navigator.geolocation) {
      setError("Geolocation is not supported by your browser.");
      setLoading(false);
      return undefined;
    }
    (async () => {
      // A tap on "Show weather for my area" is the farmer's yes.
      if (locateTick > 0) {
        setAskToLocate(false);
        setLoading(true);
        return locate();
      }
      try {
        const status = await navigator.permissions?.query({ name: "geolocation" });
        if (cancelled) return;
        if (status && status.state !== "granted") {
          setAskToLocate(true);
          setLoading(false);
          return;
        }
      } catch (e) {
        /* no Permissions API: ask on a tap rather than guess */
        setAskToLocate(true);
        setLoading(false);
        return;
      }
      locate();
    })();
    return () => {
      cancelled = true;
    };
  }, [locateTick]);

  // Close the drawer on a phone after anything is chosen in it; on a wide
  // screen it is a panel, not an overlay, and stays as the farmer left it.
  const isNarrow = () => typeof window !== "undefined" && window.innerWidth < 1024;
  const choose = (action) => () => {
    action();
    if (isNarrow()) setExtended(false);
  };

  // Escape closes the drawer, as tapping outside it does.
  useEffect(() => {
    if (!extended) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape" && isNarrow()) setExtended(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [extended]);

  const wet = weatherData ? nextWetDay(weatherData.daily) : null;
  const nav = [
    { key: "home", label: "Home", icon: ICONS.home, action: goHome, active: screen === "home" },
    { key: "new", label: "New chat", icon: ICONS.plus, action: newChat, active: screen === "ask" },
    { key: "explore", label: "Explore", icon: ICONS.compass, action: () => setScreen("explore"), active: screen === "explore" },
    { key: "news", label: "News", icon: ICONS.news, action: () => setScreen("news"), active: screen === "news" },
  ];

  return (
    <div className="flex">
      {/* The menu button on a phone, where the sidebar is a drawer. */}
      <div className="fixed left-0 top-0 z-50 p-2 lg:hidden">
        <button
          type="button"
          onClick={() => setExtended((prev) => !prev)}
          aria-label={extended ? "Close menu" : "Open menu"}
          aria-expanded={extended}
          className="grid h-touch w-touch place-items-center rounded-full text-soil-800 hover:bg-white/60"
        >
          <IoIosMenu className="h-7 w-7" />
        </button>
      </div>

      {/* Tapping anywhere outside the open drawer closes it. */}
      {extended && (
        <button
          type="button"
          aria-label="Close menu"
          tabIndex={-1}
          onClick={() => setExtended(false)}
          className="fixed inset-0 z-30 bg-soil-900/20 backdrop-blur-[2px] lg:hidden"
        />
      )}

      <nav
        aria-label="AnnaData"
        className={`glass-panel fixed left-0 top-0 z-40 h-screen transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 ${
          extended ? "translate-x-0" : "-translate-x-full"
        } ${extended ? "w-72 lg:w-64" : "lg:w-[4.25rem]"}`}
      >
        <div className="flex h-screen flex-col px-2 pb-3 pt-16 lg:pt-2">
          <div className="hidden lg:flex">
            <button
              type="button"
              onClick={() => setExtended((prev) => !prev)}
              aria-label={extended ? "Collapse sidebar" : "Expand sidebar"}
              aria-expanded={extended}
              className="grid h-touch w-touch place-items-center rounded-full text-soil-800 hover:bg-white/70"
            >
              <IoIosMenu className="h-7 w-7" />
            </button>
          </div>

          <ul className="mt-1 flex flex-col gap-1">
            {nav.map((item) => (
              <li key={item.key}>
                <button
                  type="button"
                  onClick={choose(item.action)}
                  aria-current={item.active ? "page" : undefined}
                  title={extended ? undefined : item.label}
                  className={`flex min-h-touch w-full items-center gap-3 rounded-2xl px-3 text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 ${
                    item.active ? "bg-white/85 text-leaf-800 shadow-card" : "text-soil-800 hover:bg-white/60"
                  }`}
                >
                  <span className="grid h-5 w-5 shrink-0 place-items-center">{item.icon}</span>
                  {extended && <span>{item.label}</span>}
                </button>
              </li>
            ))}
          </ul>

          <div className="mt-4 min-h-0 flex-grow overflow-y-auto">
            {extended && chats.length > 0 && (
              <section aria-label="Recent chats">
                <h2 className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-soil-600">Recent chats</h2>
                <ul className="flex flex-col gap-0.5">
                  {chats.slice(0, 30).map((chat) => (
                    <li key={chat.id}>
                      <button
                        type="button"
                        onClick={choose(() => openChat(chat.id))}
                        aria-current={screen === "chat" && chat.id === currentChatId ? "page" : undefined}
                        className={`w-full truncate rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                          screen === "chat" && chat.id === currentChatId
                            ? "bg-white/85 font-medium text-soil-900"
                            : "text-soil-800 hover:bg-white/60"
                        }`}
                      >
                        {chat.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {extended && (
              <section className="glass-soft mt-4 rounded-2xl p-3">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-soil-600">Your area</h2>
                {loading && <p className="mt-2 text-sm text-soil-600">Finding your area…</p>}
                {/* Not an error state. A farmer who declined the location
                    prompt has not broken anything - the agent asks for a
                    district in the conversation instead. */}
                {askToLocate && !error && (
                  <button
                    type="button"
                    onClick={() => setLocateTick((n) => n + 1)}
                    className="mt-2 min-h-touch text-left text-sm font-semibold text-leaf-700 underline-offset-4 hover:underline"
                  >
                    Show weather for my area
                  </button>
                )}
                {error && (
                  <p className="mt-2 text-sm text-soil-600">
                    Location unavailable — mention your district in the question and the answer will use it.
                  </p>
                )}
                {!loading && !error && weatherData && (
                  <>
                    {locationName && <p className="mt-1 text-sm font-semibold text-soil-900">{locationName}</p>}
                    <p className="mt-1 text-sm text-soil-700">
                      <span className="text-xl font-semibold text-soil-900">
                        {Math.round(weatherData.current_weather.temperature)}°C
                      </span>
                      {weatherData.daily?.temperature_2m_max?.[0] != null && (
                        <span className="ml-2 text-soil-600">
                          today {Math.round(weatherData.daily.temperature_2m_min[0])}–
                          {Math.round(weatherData.daily.temperature_2m_max[0])}°
                        </span>
                      )}
                    </p>
                    <p className="mt-2 border-t border-white/80 pt-2 text-sm text-soil-700">
                      {wet ? (
                        <>
                          <span className="font-semibold text-soil-900">Rain {describeDay(wet.date, wet.index)}</span>, about{" "}
                          {wet.mm.toFixed(0)} mm
                        </>
                      ) : (
                        <>
                          <span className="font-semibold text-soil-900">No rain expected</span> in the next seven days
                        </>
                      )}
                    </p>
                  </>
                )}
              </section>
            )}
          </div>

          {/* The account, at the bottom where a footer belongs. Absent for a
              guest: there is no account to show, and the header carries the
              way to sign in. */}
          {user && (
            <div className="mt-3 border-t border-white/80 pt-3">
              {extended && (
                <>
                  <p className="truncate px-3 text-sm font-semibold text-soil-900">{user?.name || "Your account"}</p>
                  <p className="truncate px-3 text-xs text-soil-600">
                    {[user?.district, user?.phone].filter(Boolean).join(" · ")}
                  </p>
                </>
              )}
              <button
                type="button"
                onClick={choose(signOut)}
                aria-label={extended ? undefined : "Sign out"}
                title={extended ? undefined : "Sign out"}
                className="mt-1 flex min-h-touch w-full items-center gap-3 rounded-2xl px-3 text-left text-sm text-soil-800 transition-colors hover:bg-white/60"
              >
                <FaRightFromBracket className="h-4 w-4 shrink-0" />
                {extended && "Sign out"}
              </button>
            </div>
          )}
        </div>
      </nav>
    </div>
  );
}

export default Sidebar;
