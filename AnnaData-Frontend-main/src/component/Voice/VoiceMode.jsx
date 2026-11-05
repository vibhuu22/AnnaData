import React, { useCallback, useContext, useEffect, useRef, useState } from "react";
import { Context } from "../../Context/ContextProvider";
import { Flow } from "../../Context/Flow";
import { createSpeaker, stopSpeaking, unlockAudio, speechProgress, sharedAudioContext } from "../../Config/speech";
import { followUpAsk } from "../../Config/asks";
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
 * STREAMED BOTH WAYS. The answer arrives a sentence at a time from
 * /agent/media/stream, and each sentence goes straight to the speaker, which
 * streams Gemini's voice back for it - so the first sentence is heard while the
 * rest of the answer is still being written. What the farmer is heard to have
 * said comes back first, before any of the answer.
 *
 * NOT LISTENING WHILE IT SPEAKS. An earlier version let the farmer talk over
 * an answer, as ChatGPT's and Claude's voice modes do. On a phone speaker in a
 * field that cannot be trusted: echo cancellation does not keep the answer's
 * own voice out of the microphone on every phone, and an answer that hears
 * itself interrupts itself. So the microphone is ignored while an answer is
 * spoken, and the farmer interrupts with the Talk button (or by tapping the
 * circle): it stops, listens, answers, listens again.
 *
 * SUBTITLES. What is being said is shown as it is said, the current word
 * marked - for a farmer who half-hears a word in a field, and so the screen is
 * not a static block of text while the voice runs on.
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
const DOSE_HEADING = "Registered for this pest (CIB&RC):";

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

/**
 * Which word of `words` is being said, `fraction` of the way through the
 * piece's audio. Weighted by length, with extra for the pause a comma or a
 * full stop makes, because Gemini's audio does not say where its words fall.
 */
export function wordAtFraction(words, fraction) {
  const weights = words.map((w) => w.length + 1 + (/[.!?।॥]$/.test(w) ? 5 : /[,;:]$/.test(w) ? 3 : 0));
  const total = weights.reduce((a, b) => a + b, 0);
  let reached = 0;
  const target = fraction * total;
  for (let i = 0; i < weights.length; i += 1) {
    reached += weights[i];
    if (reached >= target) return i;
  }
  return words.length - 1;
}

/** Which word contains character `char` - the phone's own voice reports it. */
export function wordAtChar(text, char) {
  return Math.max(0, text.slice(0, char).split(/\s+/).filter(Boolean).length - (/\s$/.test(text.slice(0, char)) ? 0 : 1));
}

/** What is being said, as it is said, with the current word marked. */
function Subtitles() {
  const [view, setView] = useState(null);
  useEffect(() => {
    let frame = 0;
    let last = "";
    const tick = () => {
      const progress = speechProgress();
      if (progress && progress.text) {
        const words = progress.text.split(/\s+/).filter(Boolean);
        const index =
          typeof progress.char === "number" ? wordAtChar(progress.text, progress.char) : wordAtFraction(words, progress.fraction);
        const key = `${progress.text}|${index}`;
        if (key !== last) {
          last = key;
          setView({ words, index });
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);
  if (!view) return null;
  return (
    // aria-hidden: it is being spoken already, and announcing every word
    // change would talk over it.
    <p aria-hidden="true" className="text-center text-xl leading-relaxed">
      {view.words.map((word, i) => (
        <span
          key={`${i}-${word}`}
          className={
            i < view.index
              ? "text-soil-900"
              : i === view.index
                ? "rounded-md bg-leaf-100 px-1 font-semibold text-leaf-900"
                : "text-soil-400"
          }
        >
          {word}{" "}
        </span>
      ))}
    </p>
  );
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
  // Which turn is current. An answer still arriving for a turn the farmer has
  // talked over updates the text but never speaks over the new one.
  const turnIdRef = useRef(0);
  const floorRef = useRef(0.005);
  const thresholdRef = useRef(0.02);
  const sourceRef = useRef(null);
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

  const startSpeaking = useCallback(() => {
    if (phaseRef.current === "speaking") return;
    stopLoop();
    setLevel(0);
    go("speaking");
  }, []);

  /** After the whole answer is in: say what is left, then listen again. */
  const respond = useCallback(async (result, speaker, streamed, turn) => {
    if (closedRef.current || turn !== turnIdRef.current) return;
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
    if (phaseRef.current === "paused") return;

    // Whatever the stream did not already carry: the whole answer if it was
    // not streamed, or a registered dose the final check added at the end.
    if (!streamed) {
      speaker.push(result.answer);
    } else {
      const added = result.answer.indexOf(DOSE_HEADING);
      if (added >= 0 && !streamed.includes(DOSE_HEADING)) speaker.push(result.answer.slice(added));
    }
    // The one thing still missing, said aloud - a farmer in voice mode is not
    // reading the screen. In the answer's own language.
    const ask = followUpAsk({ ...result, response: result.answer });
    if (ask) speaker.push(ask.text);

    startSpeaking();
    const { ok, reason } = await speaker.finish();
    // Ended, paused, or talked over while it was being read: stay put.
    if (closedRef.current || phaseRef.current === "paused" || turn !== turnIdRef.current) return;
    if (!ok) {
      // No voice could be had at all: the answer is on screen, and listening
      // waits until the farmer has had time to read it.
      pause(`${reason} The answer is written below.`);
      return;
    }
    turnRef.current();
  }, [pause, startSpeaking]);

  const listen = useCallback(() => {
    if (closedRef.current || !streamRef.current) return;
    const analyser = analyserRef.current;
    const stream = streamRef.current;
    const turn = ++turnIdRef.current;

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
      if (closedRef.current || turn !== turnIdRef.current) return;
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
      const speaker = createSpeaker();
      let streamed = "";
      const result = await sendRef.current({
        audio,
        quiet: true,
        // Three to five spoken sentences, not a page of markdown read aloud.
        channel: "voice",
        onHeard: (transcript) => {
          if (transcript && turn === turnIdRef.current) setHeard(transcript);
        },
        onText: (piece) => {
          if (closedRef.current || turn !== turnIdRef.current || phaseRef.current === "paused") return;
          streamed += piece;
          setReply((text) => text + piece);
          startSpeaking();
          speaker.push(piece);
        },
      });
      respond(result, speaker, streamed, turn);
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
          floorRef.current = floorSum / floorCount;
          threshold = Math.max(0.015, floorRef.current * 3);
          thresholdRef.current = threshold;
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
  }, [finishTurn, pause, respond, startSpeaking]);

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
        // The context the opening tap unlocked (see sharedAudioContext). The
        // analyser only measures the level; it is not connected to the
        // speaker, so the microphone is never played back.
        const ctx = sharedAudioContext();
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        source.connect(analyser);
        sourceRef.current = source;
        audioCtxRef.current = ctx;
        analyserRef.current = analyser;
        if (ctx.state === "suspended") {
          await Promise.race([ctx.resume().catch(() => {}), new Promise((r) => setTimeout(r, 600))]);
        }
        if (ctx.state === "suspended") {
          // Rare now the context is shared; a second tap starts it.
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
      // Shared with playback, so it is disconnected, not closed.
      try {
        sourceRef.current?.disconnect();
      } catch (e) {
        /* already gone */
      }
    };
  }, []);

  /** The orb: resume when paused, interrupt when speaking, send early when listening. */
  const tapOrb = async () => {
    unlockAudio();
    if (phase === "speaking") {
      // Interrupted: stop at once and listen. The answer still arriving, if
      // any, finishes on screen but is not spoken over the new turn.
      stopSpeaking();
      listen();
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
    speaking: "Tap Talk to interrupt",
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
          {phase === "speaking" && <Subtitles />}
          {reply && !needsSignIn && phase !== "thinking" && phase !== "speaking" && (
            <div className="max-h-[22vh] overflow-y-auto rounded-xl bg-white/90 px-4 py-3 text-sm text-soil-800 shadow-card">
              {reply.replace(/[*#_`>|]/g, "").slice(0, 900)}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-center gap-6 px-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-2">
        {/* One button whose job follows the moment: while it speaks, Talk
            interrupts it and listens; while it listens, Pause; when paused,
            Talk again. */}
        <button
          type="button"
          onClick={() => (phase === "listening" ? pause() : tapOrb())}
          disabled={phase === "thinking" || phase === "starting" || needsSignIn}
          aria-label={phase === "listening" ? "Pause listening" : phase === "speaking" ? "Interrupt and talk" : "Talk"}
          className={`flex h-16 items-center justify-center gap-2 rounded-full px-6 text-base font-semibold shadow-card disabled:opacity-40 ${
            phase === "listening"
              ? "border-[1.5px] border-soil-300 bg-white text-soil-900"
              : "bg-leaf-600 text-white hover:bg-leaf-700"
          }`}
        >
          <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 10a7 7 0 0 0 14 0" />
            <path d="M12 17v5" />
            {phase === "listening" && <path d="M3 3l18 18" />}
          </svg>
          {phase === "listening" ? "Pause" : "Talk"}
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
