import React, { useContext, useState, useRef, useEffect, useMemo, useCallback } from "react";
import { Context } from "../../Context/ContextProvider";
import { Auth } from "../../Context/AuthProvider";
import { Flow } from "../../Context/Flow";
import MediaPreview from "../MediaPreview/MediaPreview";
import Sources from "../Sources/Sources";
import Answer from "../Answer/Answer";
import Home from "../Home/Home";
import { primaryButton, textButton, SMS_NUMBER } from "../Flow/ui";
import { speak, stopSpeaking, isSpeechSupported } from "../../Config/speech";

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
    <img src={url} alt="Sent by the farmer" className="max-h-44 w-full rounded-xl object-cover" />
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

const CARD = {
  approved: "border-2 border-leaf-600",
  refusal: "border-2 border-dashed border-soil-800",
  "photo-unsure": "border-2 border-dashed border-soil-800",
  plain: "border-[1.5px] border-soil-300",
};

function Badge({ kind }) {
  const badge = BADGES[kind];
  if (!badge) return null;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-xs font-bold ${badge.className}`}>
      <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        {badge.icon}
      </svg>
      {badge.text}
    </span>
  );
}

/** "Looking this up for you…", and an honest word if it is slow. */
function Pending({ startedAt }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const left = SLOW_AFTER_MS - (Date.now() - (startedAt || Date.now()));
    if (left <= 0) {
      setSlow(true);
      return undefined;
    }
    const timer = setTimeout(() => setSlow(true), left);
    return () => clearTimeout(timer);
  }, [startedAt]);

  return (
    <div className="flex flex-col gap-3 rounded-[14px] border-[1.5px] border-soil-300 p-4" role="status" aria-live="polite">
      <div className="flex items-center gap-3">
        <div className="thinking" aria-hidden="true">
          <span className="thinking-blade" />
          <span className="thinking-blade" />
          <span className="thinking-blade" />
          <span className="thinking-blade" />
          <span className="thinking-blade" />
        </div>
        <span className="text-lg font-bold text-soil-900">Looking this up for you…</span>
      </div>
      <p className="text-sm text-soil-600">Usually 5 to 20 seconds.</p>
      {slow && (
        <p className="rounded-xl bg-soil-50 px-3.5 py-3 text-sm text-soil-700">
          <strong className="block text-soil-900">Taking longer than usual</strong>
          Some answers take up to a couple of minutes. Please keep this page open — the answer will appear here.
        </p>
      )}
    </div>
  );
}

function Main() {
  const {
    send, thread, loading, setInput, input, screen, responses, focusId,
  } = useContext(Context);
  const { user, needsOnboarding } = useContext(Auth);
  const openFlow = useContext(Flow);

  // The offer to save follows the conversation: after the newest answer, so
  // it is in view when the farmer has just read something useful.
  const latestAnswered = [...thread]
    .reverse()
    .find((turn) => !turn.pending && !turn.failed && turn.response?.trim());
  const limited = Boolean(latestAnswered?.needsSignIn);
  // "Not now" holds for this visit. Reaching the guest limit brings the card
  // back regardless, because then saving is the only way to keep asking.
  const [saveDismissed, setSaveDismissed] = useState(false);

  const [selectedImage, setSelectedImage] = useState(null);
  const [selectedAudio, setSelectedAudio] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [micError, setMicError] = useState("");
  const [speakingId, setSpeakingId] = useState(null);
  const [speechError, setSpeechError] = useState("");
  const [offline, setOffline] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const bottomRef = useRef(null);
  const autoSpokenRef = useRef(new Set());
  // Read when a recording stops, which happens in a callback created earlier.
  const draftRef = useRef({ input, selectedImage });
  draftRef.current = { input, selectedImage };

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
    async ({ text, image, audio }) => {
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        // Not sent, and said so - rather than a spinner that never resolves.
        setOffline(true);
        if (image) setSelectedImage(image);
        if (audio) setSelectedAudio(audio);
        return;
      }
      setOffline(false);
      await send({ text, image, audio });
    },
    [send]
  );

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) setSelectedImage(file);
    // Reset the input so choosing the same file twice still fires onChange.
    e.target.value = "";
  };

  /**
   * Tap to start, tap again to send. Stopping sends straight away, with
   * whatever was typed or attached alongside: for a farmer who speaks rather
   * than types, finding a second button after speaking is one step too many.
   */
  const toggleRecording = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    setMicError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const audio = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const { input: text, selectedImage: image } = draftRef.current;
        setSelectedImage(null);
        if (audio.size > 0) submit({ text, image, audio });
      };
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      setMicError("Microphone unavailable. Check the browser's permission for this site.");
    }
  };

  const handleSend = async (e) => {
    e?.preventDefault();
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const image = selectedImage;
    const audio = selectedAudio;
    setSelectedImage(null);
    setSelectedAudio(null);
    await submit({ text: input, image, audio });
  };

  const canSend = Boolean(input.trim() || selectedImage || selectedAudio);

  if (screen === "home" && user && responses.length > 0) {
    return (
      <div className="flex min-h-0 w-full flex-grow flex-col overflow-y-auto bg-white">
        <Home />
      </div>
    );
  }

  const smsLine = SMS_NUMBER
    ? `No smartphone? Text your question to ${SMS_NUMBER}.`
    : "No smartphone? AnnaData also answers by SMS.";

  const notices = (
    <>
      {offline && (
        <div className="mx-auto mb-2 w-full max-w-[750px] rounded-xl border-[1.5px] border-dashed border-soil-600 px-4 py-3" role="alert">
          <div className="text-sm font-bold text-soil-900">No internet connection</div>
          <div className="text-sm text-soil-700">
            Your question has not been sent.{" "}
            {SMS_NUMBER ? `Text it to ${SMS_NUMBER} instead — SMS works without internet.` : "SMS works without internet."}
          </div>
        </div>
      )}
      <MediaPreview
        selectedImage={selectedImage}
        selectedAudio={selectedAudio}
        clearSelectedImage={() => setSelectedImage(null)}
        clearSelectedAudio={() => setSelectedAudio(null)}
      />
      {isRecording && (
        <p className="mb-2 text-center text-sm font-semibold text-red-700">
          Listening… tap the microphone again to send.
        </p>
      )}
      {micError && <p className="mb-2 text-center text-sm text-red-700">{micError}</p>}
      {speechError && <p className="mb-2 text-center text-sm text-grain-700">{speechError}</p>}
    </>
  );

  const photoButton = (size) => (
    <label
      htmlFor="image-upload"
      title="Add a photo of the crop"
      className={`grid ${size} shrink-0 cursor-pointer place-items-center rounded-xl border-[1.5px] border-soil-400 bg-white text-soil-900 hover:bg-soil-50 focus-within:ring-2 focus-within:ring-leaf-600`}
    >
      <CameraIcon />
      <span className="sr-only">Add a photo of the crop</span>
      <input id="image-upload" type="file" accept="image/*" onChange={handleImageChange} className="sr-only" />
    </label>
  );

  if (screen === "ask") {
    return (
      <div className="flex min-h-0 w-full flex-grow flex-col overflow-y-auto bg-white">
        <div className="mx-auto flex w-full max-w-[30rem] flex-grow flex-col gap-4 px-5 pb-5 pt-6">
          <h1 className="text-2xl font-bold leading-tight text-soil-900">What is happening in your field?</h1>
          <p className="text-base text-soil-700">
            Ask in your own words — Hindi, Hinglish, Bengali, Punjabi or English. Free, and no sign-up needed to ask.
          </p>
          <div className="flex flex-col gap-2">
            <div className="text-sm font-semibold text-soil-700">For example</div>
            {EXAMPLES.map((text) => (
              <button
                key={text}
                type="button"
                onClick={() => submit({ text })}
                className="flex min-h-[48px] items-center rounded-[10px] border-[1.5px] border-soil-400 px-3.5 py-2.5 text-left text-sm text-soil-900 transition-colors hover:border-leaf-500 hover:bg-leaf-50"
              >
                {text}
              </button>
            ))}
          </div>

          <div className="min-h-4 flex-grow" />

          <div className="flex flex-col items-center gap-2">
            <button
              type="button"
              onClick={toggleRecording}
              aria-label={isRecording ? "Stop and send" : "Speak your question"}
              aria-pressed={isRecording}
              className={`grid h-20 w-20 place-items-center rounded-full text-white shadow-lift transition-colors focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-offset-2 ${
                isRecording ? "animate-pulse bg-red-600 focus-visible:ring-red-300" : "bg-leaf-600 hover:bg-leaf-700 focus-visible:ring-leaf-200"
              }`}
            >
              {isRecording ? <StopIcon size={30} /> : <MicIcon size={34} />}
            </button>
            <div className="text-sm font-semibold text-soil-900">{isRecording ? "Tap to send" : "Tap to speak"}</div>
          </div>

          <div className="chat-composer">
            {notices}
            <form onSubmit={handleSend} className="flex items-end gap-2">
              {photoButton("h-[52px] w-[52px]")}
              <label htmlFor="q" className="sr-only">
                Your question
              </label>
              <textarea
                id="q"
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) handleSend(e);
                }}
                placeholder="Or type your question…"
                className="min-h-[52px] min-w-0 flex-1 resize-none rounded-xl border-[1.5px] border-soil-400 px-3.5 py-3 text-base text-soil-900 outline-none placeholder:text-soil-500 focus:border-leaf-600 focus:ring-2 focus:ring-leaf-100"
              />
              <button
                type="submit"
                disabled={loading || !canSend}
                aria-label="Send"
                className="grid h-[52px] w-[52px] shrink-0 place-items-center rounded-xl bg-soil-900 text-white transition-colors hover:bg-soil-800 disabled:bg-soil-300"
              >
                <SendIcon />
              </button>
            </form>
          </div>
          <p className="text-center text-xs text-soil-600">{smsLine}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 w-full flex-grow flex-col overflow-hidden">
      <div className="flex flex-grow flex-col items-center overflow-y-auto bg-white px-4 py-4">
        <div className="flex w-full max-w-[42rem] flex-col gap-4">
          {thread.map((turn) => {
            const kind = kindOf(turn);
            return (
              <div key={turn.id} id={`turn-${turn.id}`} className="response-item flex flex-col gap-3">
                {/* The farmer's words, on the right, in their own script. */}
                <div className="flex max-w-[80%] flex-col gap-2 self-end rounded-[14px] rounded-br-[4px] bg-soil-100 px-3.5 py-2.5 text-base text-soil-900">
                  {turn.mediaFile && <SentMedia file={turn.mediaFile} kind={turn.mediaKind} />}
                  {turn.prompt && <p>{turn.prompt}</p>}
                  {/* What the microphone heard, so a misheard word is visible
                      rather than buried in an answer that reads as odd. */}
                  {turn.transcript && (
                    <p className="text-soil-700">
                      <span className="mr-2 text-xs uppercase tracking-wide text-soil-600">heard</span>
                      {turn.transcript}
                    </p>
                  )}
                </div>

                {turn.pending ? (
                  <Pending startedAt={turn.startedAt} />
                ) : turn.needsSignIn ? (
                  <div className="rounded-[14px] border-[1.5px] border-grain-300 bg-grain-50 p-4 text-base text-soil-900">
                    {turn.response}
                  </div>
                ) : turn.failed ? (
                  <div className="rounded-[14px] border-[1.5px] border-red-200 bg-red-50 p-4 text-base text-red-800" role="alert">
                    {turn.response}
                  </div>
                ) : (
                  <div className={`flex min-w-0 flex-col gap-2.5 rounded-[14px] p-4 ${CARD[kind]}`}>
                    {(BADGES[kind] || isSpeechSupported()) && (
                      <div className="flex items-center justify-between gap-2">
                        <Badge kind={kind} />
                        {isSpeechSupported() && (
                          <button
                            type="button"
                            onClick={() => (speakingId === turn.id ? hush() : readAloud(turn))}
                            aria-label={speakingId === turn.id ? "Stop reading the answer" : "Listen to this answer"}
                            className="ml-auto inline-flex min-h-touch min-w-touch items-center gap-1.5 rounded-[10px] border-[1.5px] border-soil-400 bg-white px-2.5 text-sm font-semibold text-soil-900 hover:bg-soil-50"
                          >
                            {speakingId === turn.id ? <StopIcon size={16} /> : <SpeakerIcon />}
                            {speakingId === turn.id ? "Stop" : "Listen"}
                          </button>
                        )}
                      </div>
                    )}
                    {turn.vision && (
                      <p className="text-sm text-soil-700">
                        <span className="font-semibold text-soil-900">From the photo: </span>
                        {[
                          turn.vision.crop !== "unknown" && turn.vision.crop,
                          turn.vision.stage !== "unknown" && turn.vision.stage,
                          turn.vision.pest !== "unknown" && `${turn.vision.pest} (${turn.vision.confidence} confidence)`,
                          turn.vision.severity !== "unknown" && turn.vision.severity,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "nothing identifiable"}
                      </p>
                    )}
                    <Answer markdown={turn.response} doseStatus={turn.doseStatus} />
                    <Sources tools={turn.toolsUsed} />
                  </div>
                )}
              </div>
            );
          })}

          {/* A guest is offered the way to save; a farmer who confirmed their
              number but left the profile halfway is offered the rest. */}
          {latestAnswered && !user && (limited || !saveDismissed) && (
            <div className="flex flex-col gap-2.5 rounded-xl bg-soil-50 p-4">
              <h2 className="text-base font-bold text-soil-900">
                {limited ? "Confirm your number to keep asking" : "Get answers for your own farm"}
              </h2>
              <p className="text-sm text-soil-700">
                Confirm your number once, then tell us your district and crops. Your questions stay saved too.
              </p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => openFlow("save")} className={`${primaryButton} !min-h-touch flex-1 !text-base`}>
                  Add farm details
                </button>
                {!limited && (
                  <button type="button" onClick={() => setSaveDismissed(true)} className={`${textButton} px-3`}>
                    Not now
                  </button>
                )}
              </div>
            </div>
          )}
          {latestAnswered && user && needsOnboarding && !saveDismissed && (
            <div className="flex flex-col gap-2.5 rounded-xl bg-soil-50 p-4">
              <h2 className="text-base font-bold text-soil-900">Finish your farm details</h2>
              <p className="text-sm text-soil-700">Add your district and crops so answers fit your own field.</p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => openFlow("profile")} className={`${primaryButton} !min-h-touch flex-1 !text-base`}>
                  Add farm details
                </button>
                <button type="button" onClick={() => setSaveDismissed(true)} className={`${textButton} px-3`}>
                  Not now
                </button>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* The follow-up row. The microphone stands in for Send until there is
          something typed or attached, as in the wireframe. */}
      <div className="chat-composer shrink-0 border-t border-soil-200 bg-white px-4 pb-3 pt-2">
        {notices}
        <form onSubmit={handleSend} className="mx-auto flex w-full max-w-[42rem] items-center gap-2">
          {photoButton("h-12 w-12")}
          <label htmlFor="followup" className="sr-only">
            Ask a follow-up
          </label>
          <input
            id="followup"
            onChange={(e) => setInput(e.target.value)}
            value={input}
            type="text"
            placeholder="Ask a follow-up…"
            className="h-12 min-w-0 flex-1 rounded-xl border-[1.5px] border-soil-400 px-3.5 text-base text-soil-900 outline-none placeholder:text-soil-500 focus:border-leaf-600 focus:ring-2 focus:ring-leaf-100"
          />
          {canSend && !isRecording ? (
            <button
              type="submit"
              disabled={loading}
              aria-label="Send"
              className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-soil-900 text-white hover:bg-soil-800 disabled:bg-soil-300"
            >
              <SendIcon />
            </button>
          ) : (
            <button
              type="button"
              onClick={toggleRecording}
              aria-label={isRecording ? "Stop and send" : "Speak a follow-up"}
              aria-pressed={isRecording}
              className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl text-white ${
                isRecording ? "animate-pulse bg-red-600" : "bg-leaf-600 hover:bg-leaf-700"
              }`}
            >
              {isRecording ? <StopIcon size={20} /> : <MicIcon size={22} />}
            </button>
          )}
        </form>
      </div>
    </div>
  );
}

export default Main;
