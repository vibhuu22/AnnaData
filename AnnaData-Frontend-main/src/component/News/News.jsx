import { t } from '../../Config/uiLanguage';
import { speak, stopSpeaking, unlockAudio } from '../../Config/speech';
import Ankur from '../Brand/Ankur';
import { FaVolumeHigh, FaStop } from 'react-icons/fa6';
import React, { useContext, useEffect, useRef, useState } from "react";
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
  if (hours < 1) return t("just now");
  if (hours < 24) return t("{hours} h ago", { hours });
  const days = Math.round(hours / 24);
  return days === 1 ? t("yesterday") : t("{days} days ago", { days });
}

function News() {
  const { user } = useContext(Auth);
  // null until the farmer picks one: until then the state is found for them.
  const [chosen, setChosen] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [playing, setPlaying] = useState(null);
  const [speechError, setSpeechError] = useState('');
  const speechTurn = useRef(0);
  const stop = () => { speechTurn.current += 1; stopSpeaking(); setPlaying(null); };
  useEffect(() => () => { speechTurn.current += 1; stopSpeaking(); }, []);
  const listen = async (item) => {
    unlockAudio();
    const wasPlaying = playing === item.link;
    stop();
    setSpeechError('');
    if (wasPlaying) return;
    const turn = speechTurn.current;
    setPlaying(item.link);
    try {
      const result = await speak(item.title, item.lang === 'hi' || /[\u0900-\u097f]/.test(item.title) ? 'hi-IN' : 'en-IN');
      if (turn !== speechTurn.current) return;
      if (result && !result.ok) setSpeechError(result.reason);
    } catch { if (turn === speechTurn.current) setSpeechError("Audio unavailable. Please read the headline."); }
    finally { if (turn === speechTurn.current) setPlaying(null); }
  };
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
  }, [chosen, userState, retry]);

  // `place` alone from a backend older than `state`.
  const found = data?.state ?? (data?.place && data.place !== "India" ? data.place : "");
  const state = chosen !== null ? chosen : found;
  const nearYou = chosen === null && data?.from === "location";

  const choose = (value) => {
    stop();
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
          <h1 className="text-2xl font-bold leading-tight text-soil-900">{t("News")}</h1>
          <p className="mt-1 text-base text-soil-700">{t("Farming news from the past week")}{data?.place && data.place !== "India" ? ` ${t("in {place}", { place: t(data.place) })}` : ` ${t("across India")}`}
            {nearYou ? `, ${t("where you are now")}` : ""}.
          </p>
        </div>
        <label className="flex flex-col gap-1 text-xs font-semibold text-soil-700">{t("Your state")}<select
            value={state}
            onChange={(e) => choose(e.target.value)}
            className="glass-soft min-h-touch rounded-xl px-3 text-sm font-medium text-soil-900"
          >
            <option value="">{t("All India")}</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {t(s)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!data && !error && (
        <div className="flex items-center gap-3 py-2" role="status">
          <Ankur pose="think" />
          <span className="wait-shimmer text-base font-semibold">{t("Finding this week's news…")}</span>
        </div>
      )}
      {(error || (data && data.items.length === 0)) && <Ankur pose="sorry" className="h-28 w-28 self-center" />}
      {error && <p role="alert" className="glass-soft rounded-2xl p-4 text-sm text-soil-800">{t(error)}</p>}
      {/* "unavailable": every news source refused just now - not the same as
          a week with no farming stories, and not worth "Try All India". */}
      {data && data.items.length === 0 && (
        <p className="glass-soft rounded-2xl p-4 text-sm text-soil-800">
          {data.unavailable
            ? t("The news could not be fetched right now. Try again in a few minutes.")
            : t("No farming news found for this week. Try All India.")}
        </p>
      )}
      {data && data.stale && data.items.length > 0 && (
        <p role="status" className="text-sm text-soil-700">{t("Showing earlier headlines; the latest could not be fetched.")}</p>
      )}

      {(error || (data && data.items.length === 0)) && <button type="button" onClick={() => setRetry((n) => n + 1)} className="min-h-touch self-start rounded-full border border-leaf-600 px-5 font-semibold text-leaf-800">{t("Try again")}</button>}
      {speechError && <p role="status" className="text-sm text-soil-800">{t(speechError)}</p>}
      {data && data.items.length > 0 && (
        <ul className="flex flex-col gap-2.5">
          {data.items.map((item) => (
            <li key={item.link} className="card-read overflow-hidden rounded-[20px] p-1 shadow-card">
              <a
                href={item.link}
                target="_blank"
                rel="noopener noreferrer"
                className="flex flex-col gap-2 rounded-[18px] p-4 no-underline hover:bg-leaf-50"
              >
                <span className="text-base font-semibold leading-snug text-soil-900">{item.title}</span>
                <span className="text-xs text-soil-600">
                  {[item.source, ago(item.published)].filter(Boolean).join(" · ")}
                </span>
              </a>
              <button type="button" onClick={() => listen(item)} aria-label={`${t(playing === item.link ? "Stop" : "Listen")}: ${item.title}`}
                aria-pressed={playing === item.link} className="mx-3 mb-3 flex min-h-touch w-[calc(100%-1.5rem)] items-center justify-center gap-3 rounded-full bg-leaf-700 px-6 font-semibold text-white hover:bg-leaf-800">
                {playing === item.link ? <FaStop aria-hidden="true" /> : <FaVolumeHigh aria-hidden="true" />}
                {t(playing === item.link ? "Stop" : "Listen")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="text-center text-xs text-soil-600">{t("Headlines from Google News. AnnaData does not check them — ask in a chat before acting on one.")}</p>
    </div>
  );
}

export default News;
