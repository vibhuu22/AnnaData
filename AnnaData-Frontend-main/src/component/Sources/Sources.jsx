import React from "react";

/**
 * Which real sources an answer was built from.
 *
 * The backend has always returned `tools_used` and the interface has always
 * thrown it away, so an answer grounded in the statutory pesticide register
 * looked exactly like one a language model made up. These chips are the
 * difference, stated where the farmer - or anyone asking how the system knows
 * what it claims - can see it.
 *
 * Only tools that fetched real data are named. "greeting", "about" and the
 * other conversational branches are not sources and would dilute the ones that
 * are.
 */
const LABELS = {
  doses: { text: "CIB&RC pesticide register", tone: "emerald" },
  msp: { text: "Minimum Support Price", tone: "emerald" },
  mandi: { text: "Mandi prices · data.gov.in", tone: "amber" },
  weather: { text: "Weather · Open-Meteo", tone: "sky" },
  soil: { text: "Soil · Earth Engine", tone: "stone" },
  kb: { text: "Scheme documents", tone: "violet" },
  image: { text: "Photo analysis", tone: "rose" },
};

const TONES = {
  emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
  amber: "bg-amber-50 text-amber-800 border-amber-200",
  sky: "bg-sky-50 text-sky-800 border-sky-200",
  stone: "bg-stone-100 text-stone-700 border-stone-300",
  violet: "bg-violet-50 text-violet-800 border-violet-200",
  rose: "bg-rose-50 text-rose-800 border-rose-200",
};

function Sources({ tools }) {
  const shown = (tools || []).filter((t) => LABELS[t]);
  if (!shown.length) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 mt-3">
      <span className="text-xs uppercase tracking-wide text-gray-400">
        Answered from
      </span>
      {shown.map((tool) => (
        <span
          key={tool}
          className={`text-xs border rounded-full px-2.5 py-1 ${TONES[LABELS[tool].tone]}`}
        >
          {LABELS[tool].text}
        </span>
      ))}
    </div>
  );
}

export default Sources;
