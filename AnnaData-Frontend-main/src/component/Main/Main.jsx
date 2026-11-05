import React, { useContext, useState, useRef, useEffect, useMemo, useCallback } from "react";
import Card from "../Card/Card";
import { IoMdSend } from "react-icons/io";
import { FaImage, FaMicrophone, FaStop, FaVolumeUp, FaRegStopCircle } from "react-icons/fa";
import { Context } from "../../Context/ContextProvider";
import MediaPreview from "../MediaPreview/MediaPreview";
import Sources from "../Sources/Sources";
import Answer from "../Answer/Answer";
import Onboarding from "../Onboarding/Onboarding";
import { Auth } from "../../Context/AuthProvider";
import { speak, stopSpeaking, isSpeechSupported } from "../../Config/speech";

// Deliberately not all English. The system answers in the script it is asked
// in, and a demo that only ever shows English questions never demonstrates the
// one capability that distinguishes it. Each card carries its own translation
// so the behaviour is legible to someone who does not read the script.
const SUGGESTIONS = [
  {
    text: "मेरे गेहूं में पीला रतुआ लग गया है, क्या करूं?",
    note: "Hindi — yellow rust in wheat",
  },
  {
    text: "Kapas me sundi lag gayi hai, kaunsi dawa daalu?",
    note: "Hinglish — bollworm in cotton",
  },
  {
    text: "What is today's mandi price for soybean in Madhya Pradesh?",
    note: "English — live market rate",
  },
  {
    text: "ਮੇਰੇ ਝੋਨੇ ਨੂੰ ਕਦੋਂ ਪਾਣੀ ਦੇਣਾ ਚਾਹੀਦਾ ਹੈ?",
    note: "Punjabi — irrigation timing for paddy",
  },
];

/**
 * A blob rendered as an image or an audio player.
 *
 * The object URL is created once per file and revoked on unmount. The previous
 * version called URL.createObjectURL inline in the render, which minted a fresh
 * URL on every re-render and never released any of them.
 */
function SentMedia({ file, kind }) {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => url && URL.revokeObjectURL(url), [url]);
  if (!url) return null;
  return kind === "image" ? (
    <img src={url} alt="Sent by the farmer" className="max-h-44 rounded-lg" />
  ) : (
    <audio controls src={url} className="h-9" />
  );
}

function Main() {
  const { send, responses, loading, setInput, input, dataSent } = useContext(Context);
  const { user, needsOnboarding } = useContext(Auth);
  const firstAnsweredTurn = responses.find(
    (turn) => !turn.pending && !turn.failed && turn.response?.trim()
  );

  const [selectedImage, setSelectedImage] = useState(null);
  const [selectedAudio, setSelectedAudio] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [micError, setMicError] = useState("");
  const [speakingId, setSpeakingId] = useState(null);
  const [speechError, setSpeechError] = useState("");

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const bottomRef = useRef(null);
  const autoSpokenRef = useRef(new Set());

  // Keep the newest turn in view as answers stream in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [responses, loading]);

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
  // who recorded their question rather than typing it is usually not reading
  // the reply either. Tracked by id so a re-render never replays an answer.
  useEffect(() => {
    const turn = responses.find(
      (t) => t.spoken && !t.pending && !t.failed && !autoSpokenRef.current.has(t.id)
    );
    if (!turn) return;
    autoSpokenRef.current.add(turn.id);
    readAloud(turn);
  }, [responses, readAloud]);

  // Silence anything still playing when the farmer leaves the page.
  useEffect(() => () => stopSpeaking(), []);

  const clearSelectedImage = () => setSelectedImage(null);
  const clearSelectedAudio = () => setSelectedAudio(null);

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) setSelectedImage(file);
    // Reset the input so choosing the same file twice still fires onChange.
    e.target.value = "";
  };

  const handleAudioRecord = async () => {
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
        setSelectedAudio(new Blob(audioChunksRef.current, { type: "audio/webm" }));
        stream.getTracks().forEach((track) => track.stop());
      };
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      // A denied microphone used to fail silently to the console, so the button
      // simply did nothing and the farmer had no idea why.
      console.error("Error accessing microphone:", err);
      setMicError("Microphone unavailable. Check the browser's permission for this site.");
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (isRecording) {
      // Sending while still recording would attach nothing. Stop first.
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const image = selectedImage;
    const audio = selectedAudio;
    setSelectedImage(null);
    setSelectedAudio(null);
    await send({ text: input, image, audio });
  };

  const canSend = Boolean(input.trim() || selectedImage || selectedAudio);

  return (
    <div className="flex-grow min-h-0 w-full flex flex-col overflow-hidden">
      <div className="flex-grow flex flex-col relative overflow-hidden">
        <div className="flex w-full flex-grow flex-col items-center overflow-y-auto bg-white p-4">
          {!dataSent ? (
            <div className="w-full flex-grow flex flex-col justify-center">
              <div className="mx-auto w-full max-w-[900px]">
                <p className="text-center text-xl text-soil-900">
                  Ask about your crop — type it, speak it, or send a photo.
                </p>
                {/* Was text-gray-400: 3.66:1 on white, which is legible at a
                    desk and gone in a field. soil-500 is the lightest tone the
                    design system allows to carry text. */}
                <p className="mx-auto mt-3 max-w-[46ch] text-center text-sm text-soil-500">
                  Answers come back in the language you asked in, with doses taken
                  from the CIB&amp;RC register rather than invented.
                </p>

                {/* Horizontally scrolled on a phone rather than stacked, so the
                    fact that there are four different scripts is visible in the
                    first screenful instead of below the fold. */}
                <div className="scrollbar-hide -mx-4 mt-8 flex gap-3 overflow-x-auto px-4 pb-2 sm:mt-10 md:mx-0 md:grid md:grid-cols-4 md:gap-4 md:px-0">
                  {SUGGESTIONS.map(({ text, note }) => (
                    <Card
                      key={text}
                      text={text}
                      note={note}
                      onClick={() => send({ text })}
                    />
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="result flex-grow w-full flex flex-col items-center">
              {responses.map((turn) => (
                <div key={turn.id} className="response-item mb-6 w-full max-w-[800px]">
                  <div className="flex items-start gap-2 mb-2">
                    {/* The farmer.
                        This was a 556 KB PNG of a robot - the template's stock
                        avatar, standing in for the person asking the question.
                        In a product whose whole posture is that the farmer
                        knows their field and the system merely looks things up,
                        drawing the farmer as a machine was the wrong way round.
                        An inline glyph costs no request at all. */}
                    <div
                      className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-soil-100 text-soil-600"
                      aria-hidden="true"
                    >
                      <svg
                        viewBox="0 0 24 24"
                        className="h-6 w-6"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <circle cx="12" cy="8.5" r="3.5" />
                        <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
                      </svg>
                    </div>
                    <div className="flex flex-col gap-2">
                      {turn.mediaFile && (
                        <SentMedia file={turn.mediaFile} kind={turn.mediaKind} />
                      )}
                      {turn.prompt && (
                        <p className="text-xl font-semibold">{turn.prompt}</p>
                      )}
                      {/* What the microphone actually heard, in the farmer's own
                          script - so a misheard word is visible rather than
                          buried in an answer that reads as slightly wrong. */}
                      {turn.transcript && (
                        <p className="text-lg text-soil-700">
                          <span className="mr-2 text-xs uppercase tracking-wide text-soil-500">
                            heard
                          </span>
                          {turn.transcript}
                        </p>
                      )}
                    </div>
                  </div>

                  {turn.vision && (
                    <div className="mb-2 ml-12 rounded-lg border border-leaf-200 bg-leaf-50 px-3 py-2 text-sm text-leaf-800">
                      <span className="font-semibold">From the photo: </span>
                      {[
                        turn.vision.crop !== "unknown" && turn.vision.crop,
                        turn.vision.stage !== "unknown" && turn.vision.stage,
                        turn.vision.pest !== "unknown" &&
                          `${turn.vision.pest} (${turn.vision.confidence} confidence)`,
                        turn.vision.severity !== "unknown" && turn.vision.severity,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "nothing identifiable"}
                    </div>
                  )}

                  <div className="result-data flex items-start gap-2">
                    {/* Placeholder for the mascot, once there is one. Until
                        then the letter अ, which is where "Annadata" starts in
                        the script most of these farmers write in. */}
                    <div
                      className="grid h-9 w-9 shrink-0 select-none place-items-center rounded-full bg-leaf-600 text-sm font-bold text-white"
                      aria-hidden="true"
                    >
                      अ
                    </div>
                    <div
                      className={`min-w-0 flex-grow rounded-card border border-soil-200 bg-soil-50 p-4 ${
                        turn.failed ? "text-red-700" : ""
                      }`}
                    >
                      {turn.pending ? (
                        // aria-live so a screen reader announces that the
                        // answer is coming; the blades themselves are
                        // decoration and are hidden from it.
                        <div
                          className="flex items-center gap-3"
                          role="status"
                          aria-live="polite"
                        >
                          <div className="thinking" aria-hidden="true">
                            <span className="thinking-blade" />
                            <span className="thinking-blade" />
                            <span className="thinking-blade" />
                            <span className="thinking-blade" />
                            <span className="thinking-blade" />
                          </div>
                          <span className="text-sm text-soil-500">
                            Finding the answer…
                          </span>
                        </div>
                      ) : (
                        <>
                          <Answer
                            markdown={turn.response}
                            doseStatus={turn.doseStatus}
                          />
                          {!turn.failed && <Sources tools={turn.toolsUsed} />}
                          {isSpeechSupported() && !turn.failed && (
                            <button
                              type="button"
                              onClick={() =>
                                speakingId === turn.id ? hush() : readAloud(turn)
                              }
                              // For a farmer who does not read, this button is
                              // how the answer gets delivered at all. It is a
                              // full-height target, not a text link.
                              className="mt-3 inline-flex min-h-touch items-center gap-2 rounded-pill border border-leaf-200 bg-white px-4 text-sm font-medium text-leaf-700 transition-colors hover:bg-leaf-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 focus-visible:ring-offset-2"
                              aria-label={
                                speakingId === turn.id
                                  ? "Stop reading the answer"
                                  : "Read the answer aloud"
                              }
                            >
                              {speakingId === turn.id ? (
                                <>
                                  <FaRegStopCircle /> Stop
                                </>
                              ) : (
                                <>
                                  <FaVolumeUp /> Listen
                                </>
                              )}
                            </button>
                          )}
                        </>
                      )}
                      </div>
                  </div>
                  {needsOnboarding && turn.id === firstAnsweredTurn?.id && (
                    <Onboarding key={user?.user_id} embedded />
                  )}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="chat-composer shrink-0 border-t border-soil-200 bg-white px-3 pt-2 sm:px-4">
        <MediaPreview
          selectedImage={selectedImage}
          selectedAudio={selectedAudio}
          clearSelectedImage={clearSelectedImage}
          clearSelectedAudio={clearSelectedAudio}
        />
        {isRecording && (
          <p className="mt-2 text-center text-sm text-red-700">
            Recording… press the microphone again to stop.
          </p>
        )}
        {micError && <p className="mt-2 text-center text-sm text-red-700">{micError}</p>}
        {speechError && (
          <p className="mt-2 text-center text-sm text-grain-700">{speechError}</p>
        )}
        {/*
          Every control here was a bare react-icon at the text's own size -
          around 17px of tappable area on a touchscreen, sitting inside a
          low-contrast grey pill. The handlers are untouched; the targets are
          not.

          The microphone is the largest thing on the bar, at 56px, and it is the
          only one that carries a filled colour. For a farmer who does not read,
          it is not one input among three - it is the way in. The camera is next
          at 44px, because a photograph of a sick plant is the highest-intent
          message this app receives. Send is last and smallest: it is the one
          action a farmer can also reach by pressing enter.
        */}
        <form
          onSubmit={handleSend}
          className="mx-auto mt-2 flex w-full max-w-[750px] items-center gap-2 rounded-pill border border-soil-200 bg-white p-2 shadow-card focus-within:border-leaf-400 focus-within:ring-2 focus-within:ring-leaf-100"
        >
          <input
            onChange={(e) => setInput(e.target.value)}
            value={input}
            type="text"
            placeholder="Ask about your crop, in any language"
            className="min-w-0 flex-grow bg-transparent px-3 text-base text-soil-800 outline-none placeholder:text-soil-400"
          />

          <label
            htmlFor="image-upload"
            title="Send a photo of the crop"
            className="grid h-touch w-touch shrink-0 cursor-pointer place-items-center rounded-full text-soil-600 transition-colors hover:bg-soil-100 hover:text-soil-800 focus-within:ring-2 focus-within:ring-leaf-500"
          >
            <FaImage className="h-5 w-5" />
            <span className="sr-only">Send a photo of the crop</span>
            <input
              id="image-upload"
              type="file"
              accept="image/*"
              onChange={handleImageChange}
              className="sr-only"
            />
          </label>

          <button
            type="button"
            onClick={handleAudioRecord}
            aria-label={isRecording ? "Stop recording" : "Record a voice message"}
            aria-pressed={isRecording}
            className={`grid h-touch-lg w-touch-lg shrink-0 place-items-center rounded-full text-white shadow-card transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${
              isRecording
                ? "animate-pulse bg-red-600 focus-visible:ring-red-600"
                : "bg-leaf-600 hover:bg-leaf-700 focus-visible:ring-leaf-600"
            }`}
          >
            {isRecording ? (
              <FaStop className="h-5 w-5" />
            ) : (
              <FaMicrophone className="h-6 w-6" />
            )}
          </button>

          <button
            type="submit"
            disabled={loading || !canSend}
            aria-label="Send"
            className="grid h-touch w-touch shrink-0 place-items-center rounded-full text-soil-600 transition-colors hover:bg-soil-100 hover:text-soil-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-500 disabled:pointer-events-none disabled:text-soil-300"
          >
            <IoMdSend className="h-6 w-6" />
          </button>
        </form>

        {/* A farmer's thumb rests at the bottom of the screen; the bar should
            not sit flush against the edge of it. Was a <br />. */}
        <div className="h-4" />
      </div>
    </div>
  );
}

export default Main;
