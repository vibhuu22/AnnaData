import React, { useState, useContext, useEffect } from "react";
import { FaPlus } from "react-icons/fa";
import { IoIosMenu } from "react-icons/io";
import { Context } from "../../Context/ContextProvider";

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

function Sidebar() {
  const [extended, setExtended] = useState(false);
  const { resetChat } = useContext(Context);

  const [weatherData, setWeatherData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [locationName, setLocationName] = useState("");

  useEffect(() => {
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

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
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
    } else {
      setError("Geolocation is not supported by your browser.");
      setLoading(false);
    }
  }, []);

  const handleNewChat = () => resetChat();

  const wet = weatherData ? nextWetDay(weatherData.daily) : null;

  return (
    <div className="flex">
      {/* Menu icon for small screens */}
      <div className="fixed left-0 top-0 z-50 p-2 lg:hidden">
        <button
          type="button"
          onClick={() => setExtended((prev) => !prev)}
          aria-label={extended ? "Close menu" : "Open menu"}
          aria-expanded={extended}
          className="grid h-touch w-touch place-items-center rounded-full text-soil-700 hover:bg-soil-100"
        >
          <IoIosMenu className="h-7 w-7" />
        </button>
      </div>

      <div
        className={`fixed left-0 top-0 z-40 h-screen border-r border-soil-200 bg-soil-50 transition-transform duration-300 ease-in-out lg:static lg:flex lg:translate-x-0 lg:flex-col ${
          extended ? "translate-x-0" : "-translate-x-full"
        } ${extended ? "w-72 sm:w-80 lg:w-64" : "lg:w-16"}`}
      >
        {/* Menu icon for large screens */}
        <div className="hidden p-2 lg:flex">
          <button
            type="button"
            onClick={() => setExtended((prev) => !prev)}
            aria-label={extended ? "Collapse sidebar" : "Expand sidebar"}
            aria-expanded={extended}
            className="grid h-touch w-touch place-items-center rounded-full text-soil-700 hover:bg-soil-100"
          >
            <IoIosMenu className="h-7 w-7" />
          </button>
        </div>

        <div className="flex h-screen flex-col px-2 pt-16 lg:pt-0">
          <div className="mb-4 flex-grow">
            <button
              type="button"
              onClick={handleNewChat}
              className="flex min-h-touch w-full items-center gap-3 rounded-pill border border-soil-200 bg-white px-3 text-left text-soil-700 transition-colors hover:bg-soil-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600"
            >
              <FaPlus className="h-4 w-4 shrink-0" />
              {extended && <span className="text-sm">New question</span>}
            </button>

            {extended && (
              <section className="mt-4 rounded-card border border-soil-200 bg-white p-3">
                <h4 className="text-xs uppercase tracking-wide text-soil-500">
                  Your area
                </h4>

                {loading && (
                  <p className="mt-2 text-sm text-soil-500">Finding your area…</p>
                )}

                {/* Not an error state. A farmer who declined the location
                    prompt has not broken anything - the agent asks for a
                    district in the conversation instead. */}
                {error && (
                  <p className="mt-2 text-sm text-soil-500">
                    Location unavailable — mention your district in the question
                    and the answer will use it.
                  </p>
                )}

                {!loading && !error && weatherData && (
                  <>
                    {locationName && (
                      <p className="mt-1 text-base font-semibold text-soil-900">
                        {locationName}
                      </p>
                    )}

                    <p className="mt-2 text-sm text-soil-700">
                      <span className="text-2xl font-semibold text-soil-900">
                        {Math.round(weatherData.current_weather.temperature)}°C
                      </span>
                      {weatherData.daily?.temperature_2m_max?.[0] != null && (
                        <span className="ml-2 text-soil-500">
                          today {Math.round(weatherData.daily.temperature_2m_min[0])}–
                          {Math.round(weatherData.daily.temperature_2m_max[0])}°
                        </span>
                      )}
                    </p>

                    <div className="mt-3 border-t border-soil-200 pt-3">
                      {wet ? (
                        <p className="text-sm text-soil-700">
                          <span className="font-semibold text-soil-900">
                            Rain {describeDay(wet.date, wet.index)}
                          </span>
                          <br />
                          about {wet.mm.toFixed(0)} mm expected
                        </p>
                      ) : (
                        <p className="text-sm text-soil-700">
                          <span className="font-semibold text-soil-900">
                            No rain expected
                          </span>
                          <br />
                          in the next seven days
                        </p>
                      )}
                    </div>
                  </>
                )}
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Sidebar;
