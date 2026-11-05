import React, { useContext, useEffect, useState } from "react";
import { Auth } from "../../Context/AuthProvider";
import { fetchNews } from "../../Config/session";
import { getCoordinates } from "../../Config/Gemini";

/**
 * Farming news for the farmer's own state: the week's headlines from Google
 * News, each opening the publisher's article.
 *
 * Which state: the one the phone is in, when location is already allowed -
 * news is about where the farmer is now. Otherwise their profile's state, then
 * the one they last chose here. Choosing a state in the list overrides it for
 * this visit.
 *
 * Headlines only, and said plainly: AnnaData does not check them. A news story
 * about a price or a pest is not advice, and the system's rules for advice -
 * doses from the register, prices from data.gov.in - do not reach a newspaper.
 * A farmer who wants to act on one can ask about it in a chat.
 */
const STATES = [
  "Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Gujarat", "Haryana", "Himachal Pradesh",
  "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab",
  "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal",
];
const KEY = "annadata.newsState";

function ago(iso) {
  if (!iso) return "";
  const hours = Math.round((Date.now() - new Date(iso).getTime()) / 3600000);
  if (Number.isNaN(hours)) return "";
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

function News() {
  const { user } = useContext(Auth);
  // null until the farmer picks one: until then the state is found for them.
  const [chosen, setChosen] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const userState = user?.state || "";

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    const load = async () => {
      if (chosen !== null) return fetchNews(chosen);
      let fallback = userState;
      try {
        fallback = fallback || window.localStorage.getItem(KEY) || "";
      } catch (e) {
        /* nothing remembered */
      }
      // Only if location is already allowed: News never asks for it.
      const coords = await getCoordinates();
      return coords ? fetchNews(fallback, coords) : fetchNews(fallback);
    };
    load()
      .then((result) => !cancelled && setData(result))
      .catch(() => !cancelled && setError("News could not be loaded just now. Please try again in a little while."));
    return () => {
      cancelled = true;
    };
  }, [chosen, userState]);

  // `place` alone from a backend older than `state`.
  const found = data?.state ?? (data?.place && data.place !== "India" ? data.place : "");
  const state = chosen !== null ? chosen : found;
  const nearYou = chosen === null && data?.from === "location";

  const choose = (value) => {
    setChosen(value);
    try {
      window.localStorage.setItem(KEY, value);
    } catch (e) {
      /* remembered for this visit only */
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-[42rem] flex-col gap-4 px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold leading-tight text-soil-900">News</h1>
          <p className="mt-1 text-base text-soil-700">
            Farming news from the past week{data?.place && data.place !== "India" ? ` in ${data.place}` : " across India"}
            {nearYou ? ", where you are now" : ""}.
          </p>
        </div>
        <label className="flex flex-col gap-1 text-xs font-semibold text-soil-700">
          Your state
          <select
            value={state}
            onChange={(e) => choose(e.target.value)}
            className="glass-soft min-h-touch rounded-xl px-3 text-sm font-medium text-soil-900"
          >
            <option value="">All India</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!data && !error && (
        <div className="flex items-center gap-3 py-2" role="status">
          <div className="wait-mark" aria-hidden="true">
            अ
          </div>
          <span className="wait-shimmer text-base font-semibold">Finding this week's news…</span>
        </div>
      )}
      {error && <p className="glass-soft rounded-2xl p-4 text-sm text-soil-800">{error}</p>}
      {data && data.items.length === 0 && (
        <p className="glass-soft rounded-2xl p-4 text-sm text-soil-800">No farming news found for this week. Try All India.</p>
      )}

      {data && data.items.length > 0 && (
        <ul className="flex flex-col gap-2.5">
          {data.items.map((item) => (
            <li key={item.link}>
              <a
                href={item.link}
                target="_blank"
                rel="noopener noreferrer"
                className="card-read flex flex-col gap-1.5 rounded-[18px] p-4 no-underline transition-transform hover:-translate-y-0.5"
              >
                <span className="text-base font-semibold leading-snug text-soil-900">{item.title}</span>
                <span className="text-xs text-soil-600">
                  {[item.source, ago(item.published)].filter(Boolean).join(" · ")}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}

      <p className="text-center text-xs text-soil-600">
        Headlines from Google News. AnnaData does not check them — ask in a chat before acting on one.
      </p>
    </div>
  );
}

export default News;
