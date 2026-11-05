import React from "react";

/**
 * Which real sources an answer was built from, as one quiet line under it:
 * "Source: CIB&RC approved-use list · Weather for your area".
 *
 * The backend has always returned `tools_used`; this is what makes an answer
 * grounded in the statutory pesticide register look different from one a
 * language model made up. Only tools that fetched real data are named.
 */
const LABELS = {
  doses: "CIB&RC approved-use list",
  msp: "Minimum Support Price",
  mandi: "data.gov.in mandi prices",
  weather: "Weather for your area",
  soil: "Soil data (Earth Engine)",
  kb: "Scheme documents",
  image: "Photo analysis",
};

export function sourceText(tools) {
  return (tools || []).filter((t) => LABELS[t]).map((t) => LABELS[t]).join(" · ");
}

function Sources({ tools }) {
  const text = sourceText(tools);
  if (!text) return null;
  return <p className="mt-3 text-xs text-soil-600">Source: {text}</p>;
}

export default Sources;
