import React from "react";
import {
  FaBug, FaCamera, FaIndianRupeeSign, FaScaleBalanced, FaCloudRain, FaSeedling, FaFlask, FaLandmark, FaVolumeHigh,
} from "react-icons/fa6";

/**
 * What AnnaData can help with, as tiles a farmer can read at a glance.
 *
 * Every tile is something the system genuinely does today - each maps to a
 * tool the agent runs (the CIB&RC register, data.gov.in mandi prices, MSP,
 * Open-Meteo, Earth Engine soil, scheme documents, the photo reader). Nothing
 * here promises a capability that is not built; new ones are added as they
 * are.
 *
 * A tile is an icon, a short name, one example question and a speaker. The
 * example is the button: a tap starts a new chat with it, so a topic always
 * comes with something to ask. The speaker reads the example aloud for a
 * farmer who would rather hear than read. The longer notes the cards used to
 * carry ("Only medicines on the government's approved list...") were the most
 * reading on the screen for the least use; what they promised is now said in
 * the answer itself.
 *
 * The MSP tile is scales, not the State Emblem a mockup used - the Emblem's
 * use is restricted by law.
 */
const TOPICS = [
  { title: "Pests and diseases", icon: FaBug, ask: "Kapas me sundi lag gayi hai, kya spray karu?" },
  { title: "Sick plant photo", icon: FaCamera, ask: null, hear: "Paudhe ki photo bhejiye" },
  { title: "Mandi prices", icon: FaIndianRupeeSign, ask: "Aaj gehu ka mandi bhav kya hai?" },
  { title: "Support price (MSP)", icon: FaScaleBalanced, ask: "Dhaan ka MSP kitna hai?" },
  { title: "Weather and spraying", icon: FaCloudRain, ask: "Is hafte barish hogi kya?" },
  { title: "Sowing and varieties", icon: FaSeedling, ask: "Gehu ki buwai kab karein?" },
  { title: "Your soil", icon: FaFlask, ask: "Meri mitti kaisi hai?" },
  { title: "Government schemes", icon: FaLandmark, ask: "PM-KISAN ke liye kaun apply kar sakta hai?" },
];

function Explore({ onAsk, onPhoto, onListen, listening }) {
  return (
    <div className="mx-auto flex w-full max-w-[42rem] flex-col gap-4 px-4 py-6">
      <div>
        <h1 className="text-2xl font-bold leading-tight text-soil-900">Explore</h1>
        <p className="mt-1 text-base text-soil-700">Tap a question to ask it, or the speaker to hear it.</p>
      </div>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {TOPICS.map(({ title, icon: Icon, ask, hear }) => {
          const spoken = ask || hear;
          return (
            <li key={title} className="glass-soft flex flex-col items-center gap-2 rounded-[20px] px-3 pb-2 pt-4 text-center">
              <Icon aria-hidden="true" className="h-9 w-9 text-leaf-700" />
              <h2 className="text-base font-bold leading-tight text-soil-900">{title}</h2>
              <button
                type="button"
                onClick={() => (ask ? onAsk(ask) : onPhoto())}
                className="flex min-h-[44px] w-full items-center justify-center rounded-xl bg-white/80 px-2 py-1.5 text-sm font-medium leading-snug text-leaf-800 transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600"
              >
                {ask ? `“${ask}”` : "Open the camera"}
              </button>
              {onListen && (
                <button
                  type="button"
                  onClick={() => onListen(spoken)}
                  aria-label={`Listen: ${spoken}`}
                  className={`grid h-11 w-11 place-items-center rounded-full transition-colors hover:bg-white/80 ${
                    listening === spoken ? "bg-white text-leaf-700" : "text-soil-800"
                  }`}
                >
                  <FaVolumeHigh aria-hidden="true" className="h-[18px] w-[18px]" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default Explore;
