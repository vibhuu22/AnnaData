import React from "react";

/**
 * What AnnaData can help with, as starting points.
 *
 * Every card is something the system genuinely does today - each maps to a
 * tool the agent runs (the CIB&RC register, data.gov.in mandi prices, MSP,
 * Open-Meteo, Earth Engine soil, scheme documents, the photo reader). Nothing
 * here promises a capability that is not built; new ones are added as they
 * are. A tap starts a new chat with the example question.
 */
const TOPICS = [
  { title: "Pests and diseases", note: "Only medicines on the government's approved list, with the dose", ask: "Kapas me sundi lag gayi hai, kya spray karu?" },
  { title: "Check a sick plant", note: "Send a photo; we say what it looks like, and what we cannot tell", ask: null },
  { title: "Mandi prices", note: "Today's rates from data.gov.in for your area", ask: "Aaj gehu ka mandi bhav kya hai?" },
  { title: "Support price (MSP)", note: "The government's guaranteed price for this season", ask: "Dhaan ka MSP kitna hai?" },
  { title: "Weather and spraying", note: "Rain and temperature for your own location", ask: "Is hafte barish hogi kya?" },
  { title: "Sowing and varieties", note: "When to sow, and what to sow", ask: "Gehu ki buwai kab karein aur kaunsi kism achhi hai?" },
  { title: "Your soil", note: "Texture, pH and organic carbon for your field's location", ask: "Meri mitti kaisi hai aur kaun si khad daalu?" },
  { title: "Government schemes", note: "What a scheme gives and who can apply", ask: "PM-KISAN ke liye kaun apply kar sakta hai?" },
];

function Explore({ onAsk, onPhoto }) {
  return (
    <div className="mx-auto flex w-full max-w-[42rem] flex-col gap-4 px-4 py-6">
      <div>
        <h1 className="text-2xl font-bold leading-tight text-soil-900">Explore</h1>
        <p className="mt-1 text-base text-soil-700">What AnnaData can help you with. Tap one to start a chat.</p>
      </div>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {TOPICS.map((topic) => (
          <li key={topic.title}>
            <button
              type="button"
              onClick={() => (topic.ask ? onAsk(topic.ask) : onPhoto())}
              className="glass-soft flex h-full w-full flex-col gap-1.5 rounded-[20px] p-4 text-left transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600"
            >
              <span className="text-base font-bold text-soil-900">{topic.title}</span>
              <span className="text-sm text-soil-700">{topic.note}</span>
              {topic.ask ? (
                <span className="mt-1 text-sm font-medium text-leaf-800">“{topic.ask}”</span>
              ) : (
                <span className="mt-1 text-sm font-medium text-leaf-800">Open a chat and tap the camera</span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default Explore;
