import React, { useCallback, useContext, useEffect, useRef, useState } from "react";
import { Context } from "../../Context/ContextProvider";
import { Flow } from "../../Context/Flow";
import { speak, stopSpeaking } from "../../Config/speech";
import { primaryButton } from "../Flow/ui";

/**
 * A spoken conversation, after ChatGPT's and Claude's voice modes.
 *
 * One microphone stream is opened when voice mode starts and kept for the whole
 * conversation. Each turn is: listen, notice the farmer has stopped talking,
 * send the recording, read the answer aloud, listen again - with no button to
 * press between turns. A farmer with mud on their hands, or who does not read,
 * can hold a whole conversation by talking.
 *
 * WHAT "PERSISTENT" MEANS HERE, AND WHAT IT DOES NOT. The microphone and the
 * conversation persist; the connection to the backend does not. Each turn is
 * still one request, answered whole and read aloud by the phone's own voice,
 * so a reply starts only once the full answer has arrived. Streaming audio both
 * ways over one open connection, so the reply can start while it is still being
 * written, is the next step and needs the backend to change - see
 * ENGINEERING_NOTES, "Voice mode".
 *
 * Turn-taking is a level detector, not speech recognition: the noise floor is
 * measured for the first moment of each turn, speech is anything well above
 * it, and a pause of PAUSE_MS after speech ends the turn. It is tuned for a
 * field, not an office - a fixed threshold that works indoors triggers on wind.
 */

const PAUSE_MS = 1300; // silence after speech that ends a turn
const CALIBRATE_MS = 350; // measuring the room before trusting the threshold
const MIN_SPEECH_MS = 250; // shorter than this is a cough, not a question
const MAX_TURN_MS = 45000; // a question, not a speech
const IDLE_MS = 15000; // nothing said: pause rather than listen forever

const LABELS = {
  starting: "Starting…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  paused: "Paused",
};

function rms(buffer) {
  let sum = 0;
  for (let i = 0; i < buffer.length; i += 1) sum += buffer[i] * buffer[i];
  return Math.sqrt(sum / buffer.length);
}

function VoiceMode({ onClose }) {
  const { send } = useContext(Context);
  const openFlow = useContext(Flow);

  const [phase, setPhase] = useState("starting");
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [notice, setNotice] = useState("");
  const [needsSignIn, setNeedsSignIn] = useState(false);

  const orbRef = useRef(null);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const frameRef = useRef(0);
  const phaseRef = useRef(phase);
  const closedRef = useRef(false);
  const sendRef = useRef(send);
  const turnRef = useRef(null);
  sendRef.current = send;

  // The phase is read inside the audio loop and after awaits, which run before
  // React re-renders - so it is written to the ref at once, not on render.
  const go = (next) => {
    phaseRef.current = next;
    setPhase(next);
  };

  const setLevel = (value) => {
    if (orbRef.current) orbRef.current.style.setProperty("--level", String(value));
  };

  const stopLoop = () => {
    cancelAnimationFrame(frameRef.current);
    frameRef.current = 0;
  };

  /** The end of a turn: stop recording; onstop sends it. */
  const finishTurn = useCallback(() => {
    stopLoop();
    setLevel(0);
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }, []);

  const pause = useCallback((message = "") => {
    go("paused");
    stopLoop();
    stopSpeaking();
    setLevel(0);
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    setNotice(message);
  }, []);

  /** Read the answer aloud, then go straight back to listening. */
  const respond = useCallback(async (result) => {
    if (closedRef.current) return;
    if (!result) {
      pause();
      return;
    }
    if (result.transcript) setHeard(result.transcript);
    setReply(result.answer || "");
    if (result.needsSignIn) {
      setNeedsSignIn(true);
      pause(result.answer);
      return;
    }
    if (result.error) {
      pause("That did not go through. Tap the circle to try again.");
      return;
    }
    go("speaking");
    const { ok, reason } = await speak(result.answer, result.replyLanguage);
    // Ended, or paused by the farmer while it was being read: stay put.
    if (closedRef.current || phaseRef.current === "paused") return;
    if (!ok) {
      // No voice for this language on this phone: the answer is on screen,
      // and listening waits until the farmer has had time to read it.
      pause(`${reason} The answer is written below.`);
      return;
    }
    turnRef.current();
  }, [pause]);

  const listen = useCallback(() => {
    if (closedRef.current || !streamRef.current) return;
    const analyser = analyserRef.current;
    const stream = streamRef.current;

    setNotice("");
    go("listening");
    chunksRef.current = [];
    let recorder;
    try {
      recorder = new MediaRecorder(stream);
    } catch (e) {
      pause("This browser cannot record audio.");
      return;
    }
    recorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      if (closedRef.current) return;
      const audio = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      if (!audio.size) {
        pause();
        return;
      }
      go("thinking");
      setReply("");
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        pause("No internet connection. Your question was not sent.");
        return;
      }
      const result = await sendRef.current({ audio, quiet: true });
      respond(result);
    };
    recorder.start();

    const buffer = new Float32Array(analyser.fftSize);
    const started = performance.now();
    let floorSum = 0;
    let floorCount = 0;
    let threshold = 0.02;
    let speechMs = 0;
    let lastVoice = 0;
    let last = started;

    const tick = (now) => {
      if (closedRef.current || phaseRef.current !== "listening") return;
      analyser.getFloatTimeDomainData(buffer);
      const level = rms(buffer);
      const dt = now - last;
      last = now;

      if (now - started < CALIBRATE_MS) {
        floorSum += level;
        floorCount += 1;
      } else {
        if (floorCount) {
          threshold = Math.max(0.015, (floorSum / floorCount) * 3);
          floorCount = 0;
        }
        if (level > threshold) {
          speechMs += dt;
          lastVoice = now;
        }
      }
      setLevel(Math.min(1, level / Math.max(threshold * 4, 0.08)));

      const spoke = speechMs >= MIN_SPEECH_MS;
      if (spoke && now - lastVoice > PAUSE_MS) return finishTurn();
      if (spoke && now - started > MAX_TURN_MS) return finishTurn();
      if (!spoke && now - started > IDLE_MS) return pause("Tap the circle when you want to talk.");
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
  }, [finishTurn, pause, respond]);

  turnRef.current = listen;

  // Open the microphone once, for the whole conversation.
  useEffect(() => {
    closedRef.current = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        if (closedRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioContextClass();
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        source.connect(analyser);
        audioCtxRef.current = ctx;
        analyserRef.current = analyser;
        if (ctx.state === "suspended") {
          // Some phones will not start audio without a second tap.
          go("paused");
          setNotice("Tap the circle to start talking.");
          return;
        }
        turnRef.current();
      } catch (e) {
        go("paused");
        setNotice("Microphone unavailable. Allow it for this site in the browser's settings.");
      }
    })();
    return () => {
      closedRef.current = true;
      stopLoop();
      stopSpeaking();
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.onstop = null;
        recorder.stop();
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
      audioCtxRef.current?.close?.();
    };
  }, []);

  /** The orb: resume when paused, interrupt when speaking, send early when listening. */
  const tapOrb = async () => {
    if (phase === "speaking") {
      stopSpeaking(); // speak() resolves, and respond() goes back to listening
      return;
    }
    if (phase === "listening") {
      finishTurn();
      return;
    }
    if (phase === "paused" && !needsSignIn) {
      if (!streamRef.current) return;
      await audioCtxRef.current?.resume?.();
      listen();
    }
  };

  const hint = {
    listening: "Tap to send now",
    speaking: "Tap to interrupt",
    paused: needsSignIn ? "" : "Tap to talk",
    thinking: "",
    starting: "",
  }[phase];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Voice conversation"
      className="body fixed inset-0 z-50 flex flex-col bg-gradient-to-b from-leaf-50 via-white to-white text-soil-900"
    >
      <div className="flex items-center justify-between px-5 pt-4">
        <span className="text-base font-bold">AnnaData</span>
        <span className="rounded-pill bg-white/80 px-3 py-1 text-xs font-semibold text-leaf-800 shadow-card">Voice</span>
      </div>

      <div className="flex flex-grow flex-col items-center justify-center gap-6 px-6">
        <button
          type="button"
          onClick={tapOrb}
          aria-label={hint || LABELS[phase]}
          className="rounded-full focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-leaf-200"
        >
          <div ref={orbRef} className="voice-orb" data-phase={phase} />
        </button>
        <div className="flex flex-col items-center gap-1 text-center" aria-live="polite">
          <div className="text-2xl font-bold">{LABELS[phase]}</div>
          {hint && <div className="text-sm text-soil-600">{hint}</div>}
        </div>

        <div className="flex w-full max-w-[28rem] flex-col gap-3">
          {heard && (
            <p className="text-center text-base text-soil-700">
              <span className="mr-1.5 text-xs uppercase tracking-wide text-soil-600">heard</span>
              {heard}
            </p>
          )}
          {notice && !needsSignIn && <p className="text-center text-sm font-semibold text-soil-800">{notice}</p>}
          {needsSignIn && (
            <div className="flex flex-col gap-2 rounded-xl bg-soil-50 p-4 text-left">
              <p className="text-sm text-soil-800">{notice}</p>
              <button
                type="button"
                onClick={() => {
                  onClose();
                  openFlow("save");
                }}
                className={`${primaryButton} !min-h-touch !text-base`}
              >
                Confirm your number
              </button>
            </div>
          )}
          {reply && !needsSignIn && phase !== "thinking" && (
            <div className="max-h-[22vh] overflow-y-auto rounded-xl bg-white/90 px-4 py-3 text-sm text-soil-800 shadow-card">
              {reply.replace(/[*#_`>|]/g, "").slice(0, 900)}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-center gap-6 px-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-2">
        <button
          type="button"
          onClick={() => (phase === "paused" ? tapOrb() : pause())}
          disabled={phase === "thinking" || phase === "starting" || needsSignIn}
          aria-label={phase === "paused" ? "Start listening" : "Pause listening"}
          className="grid h-16 w-16 place-items-center rounded-full border-[1.5px] border-soil-300 bg-white text-soil-900 shadow-card disabled:opacity-40"
        >
          <svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 10a7 7 0 0 0 14 0" />
            <path d="M12 17v5" />
            {phase !== "paused" && <path d="M3 3l18 18" />}
          </svg>
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="End voice conversation"
          className="grid h-16 w-16 place-items-center rounded-full bg-soil-900 text-white shadow-lift"
        >
          <svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M6 6l12 12" />
            <path d="M18 6L6 18" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export default VoiceMode;
