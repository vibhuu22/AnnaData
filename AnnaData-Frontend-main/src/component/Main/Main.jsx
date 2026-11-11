import { t } from '../../Config/uiLanguage';
import React, { useContext, useState, useRef, useEffect, useMemo, useCallback } from "react";
import { Context } from "../../Context/ContextProvider";
import { Auth } from "../../Context/AuthProvider";
import { Flow } from "../../Context/Flow";
import MediaPreview from "../MediaPreview/MediaPreview";
import Sources from "../Sources/Sources";
import Answer from "../Answer/Answer";
import Home from "../Home/Home";
import VoiceMode from "../Voice/VoiceMode";
import Explore from "../Explore/Explore";
import News from "../News/News";
import BottomNav from "../BottomNav/BottomNav";
import Ankur from "../Brand/Ankur";
import { FaVolumeHigh } from "react-icons/fa6";
import { useAreaWeather, nextWetDay, describeDay } from "../../Config/areaWeather";
import { primaryButton, textButton, SMS_NUMBER } from "../Flow/ui";
import { speak, stopSpeaking, isSpeechSupported, unlockAudio } from "../../Config/speech";
import { followUpAsk } from "../../Config/asks";
import { rateAnswer } from "../../Config/session";

/**
 * The conversation, laid out as in the wireframes.
 *
 *   ask   "What is happening in your field?", three examples, one large
 *         microphone, and a photo / type / send row underneath
 *   chat  the farmer's words on the right, each answer in a card whose border
 *         and badge say what kind of answer it is, and a follow-up row
 *   home  a returning farmer's welcome (Home.jsx)
 *
 * The badge is decided from data the backend sends, never from the prose:
 *   dose_status "available"        Approved dose
 *   dose_status "none_registered"  No approved spray for this  (dashed)
 *   a photo read at low confidence Photo is not enough to be sure (dashed)
 * A dashed card is the system working, not failing - it is the answer that
 * declined to guess - so it is drawn in the same ink as the others, not red.
 */

// The wireframe's examples: the three things farmers ask most - a pest, a
// sowing date, a price - in the Hinglish most of them type.
const EXAMPLES = [
  "Kapas me sundi lag gayi hai, kya spray karu?",
  "Gehu ki buwai kab karein?",
  "Aaj aalu ka mandi bhav kya hai?",
];

const SLOW_AFTER_MS = 60000;

/**
 * Thumbs up or down on an answer, stored with the SMS ratings.
 *
 * SMS farmers are asked to rate a conversation after it ends; web farmers had
 * no way to say an answer was wrong. One tap, no form - and a thumbs down
 * asks for nothing more, because a farmer who has to explain will not tap.
 */
function Rate() {
  const [rated, setRated] = useState(null);
  const send = (up) => {
    setRated(up ? "up" : "down");
    Promise.resolve()
      .then(() => rateAnswer(up))
      .catch(() => {});
  };
  if (rated) {
    return (
      <p className="mt-2 text-xs text-soil-600" role="status">
        {rated === "up" && <Ankur pose="success" className="inline-block h-14 w-14" />}
        {rated === "up" ? t("Thanks — glad it helped.") : t("Thanks for telling us. This helps us fix answers.")}
      </p>
    );
  }
  const button =
    "grid h-touch w-touch place-items-center rounded-full text-soil-600 transition-colors hover:bg-soil-100 hover:text-soil-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600";
  return (
    <div className="mt-1 flex items-center gap-1">
      <span className="mr-1 text-xs text-soil-600">{t("Was this useful?")}</span>
      <button type="button" onClick={() => send(true)} aria-label={t("Yes, useful")} className={button}>
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M7 10v11H4V10z" />
          <path d="M7 10l4-7a2 2 0 0 1 3 2l-1 5h6a2 2 0 0 1 2 2l-2 7a2 2 0 0 1-2 2H7" />
        </svg>
      </button>
      <button type="button" onClick={() => send(false)} aria-label={t("No, not useful")} className={button}>
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 14V3h3v11z" />
          <path d="M17 14l-4 7a2 2 0 0 1-3-2l1-5H5a2 2 0 0 1-2-2l2-7a2 2 0 0 1 2-2h10" />
        </svg>
      </button>
    </div>
  );
}

function FollowUpAsk({ ask, onReply }) {
  const [state, setState] = useState("");
  if (!ask) return null;
  // A tap shares the phone's location, which every later question then
  // carries - quicker for a farmer than spelling out a village.
  const share = () => {
    if (!("geolocation" in navigator)) return setState("unavailable");
    setState("asking");
    navigator.geolocation.getCurrentPosition(
      () => setState("shared"),
      () => setState("unavailable"),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    );
    return undefined;
  };
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border-[1.5px] border-dashed border-soil-300 px-3.5 py-2.5 text-sm text-soil-800">
      <span>{state === "shared" ? t("Thanks — your next answers will use your location.") : ask.text}</span>
      {ask.slot === "location" && state !== "shared" && (
        <button
          type="button"
          onClick={share}
          disabled={state === "asking"}
          className="inline-flex min-h-touch items-center gap-1.5 font-semibold text-leaf-700 underline-offset-4 hover:underline"
        >
          {state === "asking" ? t("Finding you…") : state === "unavailable" ? t("Location unavailable — type it instead") : t("Use my location")}
        </button>
      )}
      {/* The farm question: one tap answers it, in the answer's language. */}
      {ask.replies && onReply && (
        <span className="flex gap-2">
          {ask.replies.map((reply) => (
            <button
              key={reply}
              type="button"
              onClick={() => onReply(reply)}
              className="inline-flex min-h-touch items-center rounded-full border-[1.5px] border-leaf-600 px-4 font-semibold text-leaf-700 hover:bg-leaf-50"
            >
              {reply}
            </button>
          ))}
        </span>
      )}
    </div>
  );
}

function MicIcon({ size = 24 }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <path d="M12 17v5" />
    </svg>
  );
}

function StopIcon({ size = 24 }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

function CameraIcon() {
  return (
    <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
      <circle cx="12" cy="13" r="3.5" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14" />
      <path d="M13 6l6 6-6 6" />
    </svg>
  );
}

function SpeakerIcon() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 9v6h4l5 4V5L8 9z" />
      <path d="M16 9a4 4 0 0 1 0 6" />
    </svg>
  );
}

/**
 * A blob rendered as an image or an audio player. The object URL is created
 * once per file and revoked on unmount, not minted on every render.
 */
function SentMedia({ file, kind }) {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => url && URL.revokeObjectURL(url), [url]);
  if (!url) return null;
  return kind === "image" ? (
    <img src={url} alt={t("Sent by the farmer")} className="max-h-44 w-full rounded-xl object-cover" />
  ) : (
    <audio controls src={url} className="h-9 w-full" />
  );
}

/** What kind of answer this is, from the backend's own fields. */
function kindOf(turn) {
  if (turn.doseStatus === "available") return "approved";
  if (turn.doseStatus === "none_registered") return "refusal";
  const v = turn.vision;
  if (v && (v.confidence === "low" || v.pest === "unknown")) return "photo-unsure";
  return "plain";
}

const BADGES = {
  approved: {
    text: "Approved dose",
    className: "bg-leaf-600 text-white",
    icon: <path d="M5 12l5 5 9-10" />,
  },
  refusal: {
    text: "No approved spray for this",
    className: "border-[1.5px] border-soil-900 text-soil-900",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M6 6l12 12" />
      </>
    ),
  },
  "photo-unsure": {
    text: "Photo is not enough to be sure",
    className: "border-[1.5px] border-soil-900 text-soil-900",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5" />
        <path d="M12 16.5v.5" />
      </>
    ),
  },
};

// The answer is the one surface that is nearly solid (design E): advice keeps
// full contrast in sunlight. The border still says what kind of answer it is.
const CARD = {
  approved: "card-read border-2 border-leaf-600",
  refusal: "card-read border-2 border-dashed border-soil-800",
  "photo-unsure": "card-read border-2 border-dashed border-soil-800",
  plain: "card-read border border-white",
};

function Badge({ kind }) {
  const badge = BADGES[kind];
  if (!badge) return null;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-xs font-bold ${badge.className}`}>
      <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        {badge.icon}
      </svg>
      {t(badge.text)}
    </span>
  );
}

/**
 * Waiting for an answer, after ChatGPT and Claude: no box, the mark breathing
 * where the answer will appear, and one line of shimmering text.
 *
 * The wording moves on with time, and only with time. It never names a step -
 * "checking the pesticide register" - because the backend does not report its
 * steps yet, and a progress line that is not true is worse than none.
 */
const WAIT_LINES = [
  [0, "Looking this up for you"],
  [10000, "Still working on your answer"],
  [30000, "This one is taking a little longer"],
];

function Pending({ startedAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const elapsed = Math.max(0, now - (startedAt || now));
  const line = WAIT_LINES.filter(([after]) => elapsed >= after).pop()[1];
  const seconds = Math.floor(elapsed / 1000);

  return (
    <div className="flex items-start gap-3 py-1" role="status" aria-live="polite">
      <Ankur pose="think" />
      <div className="flex min-w-0 flex-col gap-1 pt-1">
        <span className="wait-shimmer text-base font-semibold">{t(line)}…</span>
        <span className="text-xs text-soil-500" aria-hidden="true">
          {seconds > 0 ? `${seconds}s · ` : ""}{t("usually 5 to 20 seconds")}</span>
        {elapsed >= SLOW_AFTER_MS && (
          <p className="glass-soft mt-2 rounded-xl px-3.5 py-3 text-sm text-soil-700">{t("Some answers take up to a couple of minutes. Please keep this page open — the answer will appear here.")}</p>
        )}
      </div>
    </div>
  );
}

/*
 * Writing an answer out. The backend sends a sentence or two at a time, so a
 * short answer used to appear all at once - which reads as pasted, not
 * written. A new answer is now revealed word by word at a steady pace: about
 * as fast as a person reads, quicker for a long answer so no one waits on it.
 * History is shown at once, and so is everything for a reader who has asked
 * their device for reduced motion.
 */
const REVEAL_MIN_CPS = 45;
const REVEAL_MAX_CPS = 200;
const REVEAL_SECONDS = 6;

/** The first `n` characters, cut back to a word and with bold or code closed. */
export function revealCut(text, n) {
  if (n >= text.length) return text;
  const space = text.lastIndexOf(" ", n);
  const line = text.lastIndexOf("\n", n);
  let cut = text.slice(0, Math.max(space, line, 0));
  if ((cut.match(/\*\*/g) || []).length % 2) cut += "**";
  if ((cut.match(/`/g) || []).length % 2) cut += "`";
  return cut;
}

// Answers already written out, kept outside the component: the chat screen
// unmounts when the farmer opens News or Explore, and component state went
// with it - so coming back wrote every answer in the chat out again.
const writtenOut = new Set();

function Reveal({ text, settled, onDone, onGrow, children }) {
  const instant =
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [shown, setShown] = useState(instant ? Number.MAX_SAFE_INTEGER : 0);
  const textRef = useRef(text);
  const settledRef = useRef(settled);
  // Kept across renders: the answer arriving in full must not start the
  // writing over from the first word.
  const positionRef = useRef(0);
  const onDoneRef = useRef(onDone);
  textRef.current = text;
  settledRef.current = settled;
  onDoneRef.current = onDone;

  // Leaving mid-way through a complete answer counts as having read it: on
  // return it is shown whole, not written out from the first word again.
  useEffect(() => () => {
    if (settledRef.current) onDoneRef.current?.();
  }, []);

  useEffect(() => {
    if (instant) return undefined;
    let frame = 0;
    let last = performance.now();
    let lastCut = -1;
    const tick = (now) => {
      const full = textRef.current;
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const cps = Math.min(REVEAL_MAX_CPS, Math.max(REVEAL_MIN_CPS, full.length / REVEAL_SECONDS));
      const position = Math.min(full.length, positionRef.current + cps * dt);
      positionRef.current = position;
      // Re-render only when a whole new word is due, not every frame.
      const cut = position >= full.length ? full.length : Math.max(full.lastIndexOf(" ", position), 0);
      if (cut !== lastCut) {
        lastCut = cut;
        setShown(position >= full.length ? full.length : position);
      }
      if (position >= full.length && settledRef.current) return;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [instant]);

  const done = settled && shown >= text.length;
  useEffect(() => {
    if (done) onDone?.();
  }, [done, onDone]);
  useEffect(() => {
    if (!done) onGrow?.();
  }, [shown, done, onGrow]);
  return children(done ? text : revealCut(text, shown), done);
}

function Main() {
  const {
    send, thread, loading, setInput, input, screen, responses, focusId, newChat,
    chats = [], openChat,
  } = useContext(Context);
  const area = useAreaWeather();
  const [listening, setListening] = useState(null);
  const { user, needsOnboarding } = useContext(Auth);
  const openFlow = useContext(Flow);

  // The offer to save follows the conversation: after the newest answer, so
  // it is in view when the farmer has just read something useful.
  // New answers whose writing-out has finished. Until then, what depends on
  // the whole answer - the badge, Listen, rating, the offers below - waits.
  const [revealed, setRevealed] = useState(() => new Set(writtenOut));
  const markRevealed = useCallback((id) => {
    writtenOut.add(id);
    setRevealed((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  }, []);
  const latestAnswered = [...thread]
    .reverse()
    .find(
      (turn) =>
        !turn.pending && !turn.streaming && !turn.failed && turn.response?.trim() &&
        (!turn.live || turn.needsSignIn || revealed.has(turn.id))
    );
  const limited = Boolean(latestAnswered?.needsSignIn);
  // "Not now" holds for this visit. Reaching the guest limit brings the card
  // back regardless, because then saving is the only way to keep asking.
  const [saveDismissed, setSaveDismissed] = useState(false);

  const [selectedImage, setSelectedImage] = useState(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [speakingId, setSpeakingId] = useState(null);
  const [speechError, setSpeechError] = useState("");
  const [offline, setOffline] = useState(false);

  const bottomRef = useRef(null);
  // Keep the words being written in view.
  const grow = useCallback(() => bottomRef.current?.scrollIntoView({ block: "end" }), []);
  const writingCard = (text) => (
    <div className="card-read flex min-w-0 flex-col gap-2.5 rounded-[22px] border border-white p-4" aria-busy="true">
      <Answer markdown={text} doseStatus={null} />
      <span className="wait-shimmer text-xs font-semibold">{t("Writing…")}</span>
    </div>
  );
  const autoSpokenRef = useRef(new Set());

  // Keep the newest turn in view as answers arrive.
  useEffect(() => {
    if (screen === "chat") bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [responses, loading, screen]);

  // An earlier question opened from the home screen.
  useEffect(() => {
    if (focusId && screen === "chat") {
      document.getElementById(`turn-${focusId}`)?.scrollIntoView({ block: "start" });
    }
  }, [focusId, screen]);

  useEffect(() => {
    const back = () => setOffline(false);
    window.addEventListener("online", back);
    return () => window.removeEventListener("online", back);
  }, []);

  const readAloud = useCallback(async (turn) => {
    setSpeechError("");
    setSpeakingId(turn.id);
    const { ok, reason } = await speak(turn.response, turn.replyLanguage);
    if (!ok) setSpeechError(reason);
    setSpeakingId((current) => (current === turn.id ? null : current));
  }, []);

  const hush = () => {
    stopSpeaking();
    setSpeakingId(null);
  };

  // An answer to a spoken question is read back without being asked. A farmer
  // who recorded their question is usually not reading the reply either.
  useEffect(() => {
    const turn = responses.find(
      (t) => t.spoken && !t.pending && !t.failed && !autoSpokenRef.current.has(t.id)
    );
    if (!turn) return;
    autoSpokenRef.current.add(turn.id);
    readAloud(turn);
  }, [responses, readAloud]);

  useEffect(() => () => stopSpeaking(), []);

  /** Send, unless there is plainly no connection to send it over. */
  const submit = useCallback(
    async ({ text, image }) => {
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        // Not sent, and said so - rather than a spinner that never resolves.
        setOffline(true);
        if (image) setSelectedImage(image);
        return;
      }
      setOffline(false);
      await send({ text, image });
    },
    [send]
  );

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) setSelectedImage(file);
    // Reset the input so choosing the same file twice still fires onChange.
    e.target.value = "";
  };

  /** Voice is a conversation, not a voice note: it opens voice mode. */
  const [micContext, setMicContext] = useState(null);
  const openVoice = () => {
    // From the tap itself, so an iPhone will play the spoken answers later.
    unlockAudio();
    // And the microphone's own audio context, created in the same tap so an
    // iPhone lets it run. Its own, not the one speech plays through: turning
    // the microphone on can freeze a context that already exists on an
    // iPhone, which left the level meter reading silence while the farmer
    // spoke - voice mode listened for ever and never sent.
    let context = null;
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      context = AudioContextClass ? new AudioContextClass() : null;
      context?.resume?.();
    } catch (e) {
      context = null;
    }
    setMicContext(context);
    stopSpeaking();
    setSpeakingId(null);
    setVoiceOpen(true);
  };

  const handleSend = async (e) => {
    e?.preventDefault();
    const image = selectedImage;
    setSelectedImage(null);
    await submit({ text: input, image });
  };

  const canSend = Boolean(input.trim() || selectedImage);
  const voice = voiceOpen && <VoiceMode micContext={micContext} onClose={() => setVoiceOpen(false)} />;

  /** Read a starting question aloud, for a farmer who would rather hear it. */
  const listen = async (text) => {
    unlockAudio();
    stopSpeaking();
    setListening(text);
    const result = await speak(text, "hi-IN");
    if (result && !result.ok) setSpeechError(result.reason);
    setListening((current) => (current === text ? null : current));
  };

  // Every screen but the chat itself carries the phone's bottom bar; the
  // padding keeps content clear of it (none on a wide screen, where it hides).
  const withNav = (content) => (
    <div className="flex min-h-0 w-full flex-grow flex-col overflow-y-auto pb-24 lg:pb-0">
      {voice}
      {content}
      <BottomNav onTalk={openVoice} />
    </div>
  );

  if (screen === "explore" || screen === "news") {
    return withNav(
      screen === "explore" ? (
        <Explore
          onAsk={(text) => {
            newChat();
            submit({ text });
          }}
          onPhoto={newChat}
          onListen={listen}
          listening={listening}
        />
      ) : (
        <News />
      )
    );
  }

  if (screen === "home" && user && responses.length > 0) {
    return withNav(<Home />);
  }

  const smsLine = SMS_NUMBER
    ? t("No smartphone? Text your question to {number}.", { number: SMS_NUMBER })
    : t("No smartphone? AnnaData also answers by SMS.");

  const notices = (
    <>
      {offline && (
        <div className="mx-auto mb-2 w-full max-w-[750px] rounded-xl border-[1.5px] border-dashed border-soil-600 px-4 py-3" role="alert">
          <div className="text-sm font-bold text-soil-900">{t("No internet connection")}</div>
          <div className="text-sm text-soil-700">{t("Your question has not been sent.")}{" "}
            {SMS_NUMBER ? t("Text it to {number} instead — SMS works without internet.", { number: SMS_NUMBER }) : t("SMS works without internet.")}
          </div>
        </div>
      )}
      <MediaPreview
        selectedImage={selectedImage}
        selectedAudio={null}
        clearSelectedImage={() => setSelectedImage(null)}
        clearSelectedAudio={() => {}}
      />
      {speechError && <p className="mb-2 text-center text-sm text-grain-700">{t(speechError)}</p>}
    </>
  );

  const photoButton = (size) => (
    <label
      htmlFor="image-upload"
      title={t("Add a photo of the crop")}
      className={`grid ${size} shrink-0 cursor-pointer place-items-center rounded-full bg-white/80 text-soil-900 hover:bg-white focus-within:ring-2 focus-within:ring-leaf-600`}
    >
      <CameraIcon />
      <span className="sr-only">{t("Add a photo of the crop")}</span>
      <input id="image-upload" type="file" accept="image/*" onChange={handleImageChange} className="sr-only" />
    </label>
  );

  if (screen === "ask") {
    const weather = area.status === "ready" ? area.data : null;
    const wet = weather ? nextWetDay(weather.daily) : null;
    return withNav(
      <div className="mx-auto flex w-full max-w-[30rem] flex-grow flex-col gap-4 px-5 pb-5 pt-5">
        {/* Ankur greets; the question stays the screen's heading. */}
        <div className="flex items-center gap-3">
          <Ankur className="h-24 w-24" />
          <div>
            <p className="text-sm text-soil-700">{t("Namaskar")}{user?.name ? `, ${user.name}` : ""}</p>
            <h1 className="text-2xl font-bold leading-tight text-soil-900">{t("What is happening in your field?")}</h1>
          </div>
        </div>
        <p className="text-base text-soil-700">{t("Ask in your own words — Hindi, Hinglish, Bengali, Punjabi or English. Free, and no sign-up needed to ask.")}</p>

        {/* The weather where they are, once location is allowed - the same
            reading as the menu's "Your area", fetched once for both. */}
        {weather?.current_weather && (
          <p className="glass-soft rounded-2xl px-4 py-2.5 text-sm text-soil-800">
            <span className="font-semibold text-soil-900">
              {area.place || t("Your area")} · {Math.round(weather.current_weather.temperature)}°C
            </span>
            {" · "}
            {wet ? t("rain {day}, about {mm} mm", { day: describeDay(wet.date, wet.index), mm: wet.mm.toFixed(0) }) : t("no rain expected this week")}
          </p>
        )}

        {/* Each example can be tapped to ask, or heard first. */}
        <div className="flex flex-col gap-2">
          <div className="text-sm font-semibold text-soil-700">{t("Tap to ask, or listen")}</div>
          {EXAMPLES.map((text) => (
            <div key={text} className="glass-soft flex items-center gap-1 rounded-2xl py-1 pl-4 pr-1">
              <button
                type="button"
                onClick={() => submit({ text })}
                className="flex min-h-[44px] flex-1 items-center py-1.5 text-left text-sm text-soil-900"
              >
                {text}
              </button>
              <button
                type="button"
                onClick={() => listen(text)}
                aria-label={`${t("Listen")}: ${text}`}
                className={`grid h-11 w-11 shrink-0 place-items-center rounded-full transition-colors hover:bg-white/80 ${
                  listening === text ? "bg-white text-leaf-700" : "text-soil-800"
                }`}
              >
                <FaVolumeHigh aria-hidden="true" className="h-[18px] w-[18px]" />
              </button>
            </div>
          ))}
        </div>

        {chats.length > 0 && (
          <section aria-label={t("Recent chats")} className="flex flex-col gap-2">
            <h2 className="text-sm font-semibold text-soil-700">{t("Recent chats")}</h2>
            {chats.slice(0, 3).map((chat) => (
              <button
                key={chat.id}
                type="button"
                onClick={() => openChat?.(chat.id)}
                className="glass-soft flex min-h-[44px] items-center truncate rounded-2xl px-4 py-2.5 text-left text-sm text-soil-900"
              >
                {chat.title}
              </button>
            ))}
          </section>
        )}

        <div className="min-h-4 flex-grow" />

        {/* On a phone the bottom bar carries the microphone; this one is for
            a wide screen, where there is no bottom bar. */}
        <div className="hidden flex-col items-center gap-2 lg:flex">
          <button
            type="button"
            onClick={openVoice}
            aria-label={t("Talk to AnnaData")}
            className="grid h-20 w-20 place-items-center rounded-full bg-leaf-600 text-white shadow-lift transition-colors hover:bg-leaf-700 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-leaf-200 focus-visible:ring-offset-2"
          >
            <MicIcon size={34} />
          </button>
          <div className="text-sm font-semibold text-soil-900">{t("Tap to talk")}</div>
        </div>

        {/* On a phone the screen is taller than the window; pinned just
            above the bottom bar, the typing box stays in view without
            scrolling. A wide screen has no bar and lets it sit in flow. */}
        <div className="chat-composer sticky bottom-0 z-10 lg:static">
          {notices}
          <form onSubmit={handleSend} className="glass flex items-end gap-2 rounded-[28px] p-2 shadow-lift">
            {photoButton("h-11 w-11")}
            <label htmlFor="q" className="sr-only">{t("Your question")}</label>
            <textarea
              id="q"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) handleSend(e);
              }}
              placeholder={t("Or type your question…")}
              className="min-h-[44px] min-w-0 flex-1 resize-none bg-transparent px-2 py-2.5 text-base text-soil-900 outline-none placeholder:text-soil-600"
            />
            <button
              type="submit"
              disabled={loading || !canSend}
              aria-label={t("Send")}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-leaf-600 text-white transition-colors hover:bg-leaf-700 disabled:bg-soil-300"
            >
              <SendIcon />
            </button>
          </form>
        </div>
        <p className="text-center text-xs text-soil-600">{smsLine}</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 w-full flex-grow flex-col overflow-hidden">
      {voice}
      <div className="flex flex-grow flex-col items-center overflow-y-auto px-4 py-4">
        <div className="flex w-full max-w-[42rem] flex-col gap-4">
          {thread.map((turn) => {
            const kind = kindOf(turn);
            const finalCard = (
                  <div className={`flex min-w-0 flex-col gap-2.5 rounded-[22px] p-4 ${CARD[kind]}`}>
                    {(BADGES[kind] || isSpeechSupported()) && (
                      <div className="flex items-center justify-between gap-2">
                        <Badge kind={kind} />
                        {isSpeechSupported() && (
                          <button
                            type="button"
                            onClick={() => {
                              unlockAudio();
                              if (speakingId === turn.id) hush();
                              else readAloud(turn);
                            }}
                            aria-label={speakingId === turn.id ? t("Stop reading the answer") : t("Listen to this answer")}
                            className="ml-auto inline-flex min-h-touch min-w-touch items-center gap-1.5 rounded-[10px] border-[1.5px] border-soil-400 bg-white px-2.5 text-sm font-semibold text-soil-900 hover:bg-soil-50"
                          >
                            {speakingId === turn.id ? <StopIcon size={16} /> : <SpeakerIcon />}
                            {speakingId === turn.id ? t("Stop") : t("Listen")}
                          </button>
                        )}
                      </div>
                    )}
                    {(turn.vision || turn.diagnosis || turn.mediaKind === "image") && (
                      <h2 className="text-lg font-bold text-soil-900">
                        {typeof turn.diagnosis?.settled === "string" && turn.diagnosis.settled.trim()
                          ? <>{t("Identified cause")}: {turn.diagnosis.settled}</>
                          : t("Possible causes")}
                      </h2>
                    )}
                    {kind === "refusal" && <Ankur pose="sorry" />}
                    {turn.vision && (
                      <p className="text-sm text-soil-700">
                        <span className="font-semibold text-soil-900">{t("From the photo:")}{" "}</span>
                        {[
                          turn.vision.crop !== "unknown" && turn.vision.crop,
                          turn.vision.stage !== "unknown" && turn.vision.stage,
                          turn.vision.pest !== "unknown" && `${turn.vision.pest} (${t("{level} confidence", { level: t(turn.vision.confidence || "low") })})`,
                          turn.vision.severity !== "unknown" && turn.vision.severity,
                        ]
                          .filter(Boolean)
                          .join(" · ") || t("nothing identifiable")}
                      </p>
                    )}
                    <Answer markdown={turn.response} doseStatus={turn.doseStatus} />
                    <Sources tools={turn.toolsUsed} />
                    <Rate />
                  </div>
            );
            return (
              <div key={turn.id} id={`turn-${turn.id}`} className="response-item flex flex-col gap-3">
                {/* The farmer's words, on the right, in their own script. */}
                <div className="glass-soft flex max-w-[80%] flex-col gap-2 self-end rounded-[20px] rounded-br-[6px] px-4 py-2.5 text-base text-soil-900 shadow-card">
                  {turn.mediaFile && <SentMedia file={turn.mediaFile} kind={turn.mediaKind} />}
                  {turn.prompt && <p>{turn.prompt}</p>}
                  {/* What the microphone heard, so a misheard word is visible
                      rather than buried in an answer that reads as odd. */}
                  {turn.transcript && (
                    <p className="text-soil-700">
                      <span className="mr-2 text-xs uppercase tracking-wide text-soil-600">{t("heard")}</span>
                      {turn.transcript}
                    </p>
                  )}
                </div>

                {turn.pending ? (
                  <Pending startedAt={turn.startedAt} />
                ) : turn.needsSignIn ? (
                  <div className="card-read rounded-[22px] border-[1.5px] border-grain-300 p-4 text-base text-soil-900">
                    {turn.response}
                  </div>
                ) : turn.streaming && !turn.live ? (
                  // Still being written: the text as far as it has come, with
                  // nothing that depends on the whole answer - no badge, no
                  // Listen, no rating - until it is complete and checked.
                  writingCard(turn.response)
                ) : turn.failed ? (
                  <div className="card-read rounded-[22px] border-[1.5px] border-red-200 p-4 text-base text-red-800" role="alert">
                    <Ankur pose="sorry" />
                    {turn.response}
                  </div>
                ) : turn.live && !revealed.has(turn.id) && !turn.failed && !turn.needsSignIn ? (
                  // A new answer is written out at a steady pace, as if being
                  // written for this farmer, whatever speed it arrives at.
                  <Reveal
                    text={turn.response}
                    settled={!turn.streaming}
                    onDone={() => markRevealed(turn.id)}
                    onGrow={grow}
                  >
                    {(shown, done) => (done ? finalCard : writingCard(shown))}
                  </Reveal>
                ) : (
                  finalCard
                )}
              </div>
            );
          })}

          {latestAnswered && !latestAnswered.needsSignIn && (
            <FollowUpAsk key={latestAnswered.id} ask={followUpAsk(latestAnswered)} onReply={(text) => send({ text })} />
          )}

          {/* A guest is offered the way to save; a farmer who confirmed their
              number but left the profile halfway is offered the rest. */}
          {latestAnswered && !user && (limited || !saveDismissed) && (
            <div className="glass-soft flex flex-col gap-2.5 rounded-[20px] p-4">
              <h2 className="text-base font-bold text-soil-900">
                {limited ? t("Confirm your number to keep asking") : t("Get answers for your own farm")}
              </h2>
              <p className="text-sm text-soil-700">{t("Confirm your number once, then tell us your district and crops. Your questions stay saved too.")}</p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => openFlow("save")} className={`${primaryButton} !min-h-touch flex-1 !text-base`}>{t("Add farm details")}</button>
                {!limited && (
                  <button type="button" onClick={() => setSaveDismissed(true)} className={`${textButton} px-3`}>{t("Not now")}</button>
                )}
              </div>
            </div>
          )}
          {latestAnswered && user && needsOnboarding && !saveDismissed && (
            <div className="glass-soft flex flex-col gap-2.5 rounded-[20px] p-4">
              <h2 className="text-base font-bold text-soil-900">{t("Finish your farm details")}</h2>
              <p className="text-sm text-soil-700">{t("Add your district and crops so answers fit your own field.")}</p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => openFlow("profile")} className={`${primaryButton} !min-h-touch flex-1 !text-base`}>{t("Add farm details")}</button>
                <button type="button" onClick={() => setSaveDismissed(true)} className={`${textButton} px-3`}>{t("Not now")}</button>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* The follow-up row. The microphone stands in for Send until there is
          something typed or attached, as in the wireframe. */}
      <div className="chat-composer shrink-0 px-3 pb-3 pt-1">
        {notices}
        <form onSubmit={handleSend} className="glass mx-auto flex w-full max-w-[42rem] items-center gap-2 rounded-[30px] p-2 shadow-lift">
          {photoButton("h-11 w-11")}
          <label htmlFor="followup" className="sr-only">{t("Ask a follow-up")}</label>
          <input
            id="followup"
            onChange={(e) => setInput(e.target.value)}
            value={input}
            type="text"
            placeholder={t("Ask a follow-up…")}
            className="h-11 min-w-0 flex-1 bg-transparent px-2 text-base text-soil-900 outline-none placeholder:text-soil-600"
          />
          {canSend ? (
            <button
              type="submit"
              disabled={loading}
              aria-label={t("Send")}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-leaf-600 text-white hover:bg-leaf-700 disabled:bg-soil-300"
            >
              <SendIcon />
            </button>
          ) : (
            <button
              type="button"
              onClick={openVoice}
              aria-label={t("Talk to AnnaData")}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-leaf-600 text-white hover:bg-leaf-700"
            >
              <MicIcon size={22} />
            </button>
          )}
        </form>
      </div>
    </div>
  );
}

export default Main;
