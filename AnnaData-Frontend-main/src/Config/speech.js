import { getApiUrl } from "./api";
import { askHeaders } from "./session";

/**
 * Reading an answer aloud, in the farmer's own language.
 *
 * A farmer who sends a voice note rather than typing often cannot comfortably
 * read the reply either, so an answer they can only read is half a feature.
 *
 * GEMINI'S VOICE FIRST, THE PHONE'S AS A FALLBACK. The phone's own speech
 * synthesis was the only voice until farmers heard it: robotic, Hinglish read
 * in an English accent, and on many phones no Bengali or Punjabi voice at all.
 * Answers are now spoken by the backend's /speak (Gemini TTS) and played here.
 * The phone's voice is kept for when /speak is unreachable, so an outage makes
 * the answer sound worse rather than go silent.
 *
 * PIECE BY PIECE. The answer is cut at sentence ends into pieces; the first is
 * kept short so speech starts quickly, and each next piece is fetched while
 * the one before it plays.
 *
 * Played through Web Audio rather than an <audio> element because iPhones only
 * allow sound that a tap started: an AudioContext resumed once by a tap
 * (unlockAudio) keeps playing later answers, where an <audio> element started
 * after a network wait is refused.
 *
 * With the phone's voice, which voices exist is entirely up to the device.
 * Where the language is missing we say so rather than reading Devanagari with
 * an English voice, which produces sounds no one can follow.
 */

const SUPPORTED = typeof window !== "undefined" && "speechSynthesis" in window;

/**
 * Voices load asynchronously in Chrome: the first call to getVoices() returns
 * an empty list and the real one arrives on the voiceschanged event. Anything
 * that asks before then would conclude the device has no Indian voices at all.
 */
export function loadVoices() {
  if (!SUPPORTED) return Promise.resolve([]);
  const existing = window.speechSynthesis.getVoices();
  if (existing.length) return Promise.resolve(existing);
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      resolve(window.speechSynthesis.getVoices());
    };
    window.speechSynthesis.addEventListener("voiceschanged", done, { once: true });
    // Some builds never fire the event when there is nothing to load.
    setTimeout(done, 1000);
  });
}

/**
 * The best available voice for a BCP-47 tag.
 *
 * An exact match wins; otherwise any voice for the same language is accepted -
 * "hi-IN" is what we ask for, and a device offering plain "hi" reads it just as
 * well. Never falls back across languages.
 */
export function voiceFor(voices, lang) {
  if (!lang) return null;
  const wanted = lang.toLowerCase();
  const base = wanted.split("-")[0];
  return (
    voices.find((v) => v.lang && v.lang.toLowerCase() === wanted) ||
    voices.find((v) => v.lang && v.lang.toLowerCase().replace("_", "-").startsWith(base)) ||
    null
  );
}

/**
 * Markdown as spoken words.
 *
 * The answer is written for a screen - headings, bold, bullets - and a speech
 * engine reads those characters out literally ("hash hash hash", "star star").
 * Structure becomes pauses instead, which is what a heading means out loud.
 */
export function speakableText(markdown) {
  if (!markdown) return "";
  return markdown
    .replace(/```[\s\S]*?```/g, " ")          // code fences
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")    // images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")  // links keep their text
    .replace(/^#{1,6}\s*/gm, "")              // headings
    .replace(/\*\*([^*]*)\*\*/g, "$1")
    .replace(/\*([^*]*)\*/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "")            // bullets
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*\|.*\|\s*$/gm, " ")         // table rows do not read aloud
    .replace(/\n{2,}/g, ". ")                 // a blank line is a pause
    .replace(/\n/g, ". ")
    .replace(/\.\s*\.(\s*\.)*/g, ". ")        // collapse the runs that creates
    .replace(/\s{2,}/g, " ")
    .trim();
}

const AudioContextClass =
  typeof window !== "undefined" ? window.AudioContext || window.webkitAudioContext : null;

let context = null;
let session = 0;
let playing = null;
let aborter = null;

function audioContext() {
  if (!AudioContextClass) return null;
  if (!context) {
    try {
      context = new AudioContextClass();
    } catch (e) {
      return null;
    }
  }
  return context;
}

/**
 * Call from a tap. Resumes audio and plays a moment of silence, which is what
 * an iPhone needs before it will play anything that was not started by a tap.
 */
export function unlockAudio() {
  const ctx = audioContext();
  if (!ctx) return;
  try {
    if (ctx.state === "suspended") ctx.resume();
    const silence = ctx.createBuffer(1, 1, 22050);
    const source = ctx.createBufferSource();
    source.buffer = silence;
    source.connect(ctx.destination);
    source.start(0);
  } catch (e) {
    /* nothing to unlock */
  }
}

export function isSpeechSupported() {
  return SUPPORTED || Boolean(AudioContextClass);
}

export function stopSpeaking() {
  session += 1;
  aborter?.abort();
  aborter = null;
  try {
    playing?.stop();
  } catch (e) {
    /* already stopped */
  }
  playing = null;
  if (SUPPORTED) window.speechSynthesis.cancel();
}

/**
 * An answer cut into pieces at sentence ends: a short first piece so speech
 * starts quickly, then longer ones. A sentence longer than a piece is cut at
 * a comma or a space rather than mid-word.
 */
export function piecesOf(text, first = 160, rest = 400) {
  const sentences = (String(text || "").match(/(?:[^.!?।॥\n]|\.(?=\d))+[.!?।॥]*\s*/g) || [])
    .map((s) => s.trim())
    .filter(Boolean);
  const pieces = [];
  let current = "";
  const limit = () => (pieces.length === 0 ? first : rest);
  const push = () => {
    if (current.trim()) pieces.push(current.trim());
    current = "";
  };
  sentences.forEach((sentence) => {
    let s = sentence;
    while (s.length > limit()) {
      push();
      const cut = Math.max(s.lastIndexOf(",", limit()), s.lastIndexOf(" ", limit()));
      const at = cut > limit() / 3 ? cut + 1 : limit();
      pieces.push(s.slice(0, at).trim());
      s = s.slice(at).trim();
    }
    if (current && (current + " " + s).length > limit()) push();
    current = current ? `${current} ${s}` : s;
  });
  push();
  return pieces;
}

async function fetchPiece(text, lang, signal) {
  const response = await fetch(`${getApiUrl()}/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...askHeaders() },
    body: JSON.stringify({ text, lang }),
    signal,
  });
  if (!response.ok) throw new Error(`speak ${response.status}`);
  const bytes = await response.arrayBuffer();
  const ctx = audioContext();
  // The callback form, because older Safari does not return a promise.
  return new Promise((resolve, reject) => ctx.decodeAudioData(bytes, resolve, reject));
}

function play(buffer, mine) {
  return new Promise((resolve) => {
    if (mine !== session) return resolve();
    const ctx = audioContext();
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.onended = () => resolve();
    playing = source;
    source.start(0);
  });
}

/**
 * Read an answer aloud with Gemini's voice, falling back to the phone's.
 * Resolves when it finishes, is stopped, or cannot start: { ok, reason }.
 */
export async function speak(markdown, lang) {
  const text = speakableText(markdown);
  if (!text) return { ok: false, reason: "Nothing to read." };
  stopSpeaking();
  const mine = session;
  const pieces = piecesOf(text);
  const ctx = audioContext();
  if (!ctx || typeof fetch !== "function") return speakOnDevice(text, lang);

  aborter = new AbortController();
  const { signal } = aborter;
  let index = 0;
  try {
    if (ctx.state === "suspended") await ctx.resume().catch(() => {});
    let next = fetchPiece(pieces[0], lang, signal);
    for (index = 0; index < pieces.length; index += 1) {
      const buffer = await next;
      if (mine !== session) return { ok: true };
      if (index + 1 < pieces.length) {
        next = fetchPiece(pieces[index + 1], lang, signal);
        next.catch(() => {}); // handled when awaited
      }
      await play(buffer, mine);
      if (mine !== session) return { ok: true };
    }
    return { ok: true };
  } catch (e) {
    if (mine !== session) return { ok: true }; // stopped by the farmer
    console.warn("Spoken answer unavailable, using the phone's voice:", e.message);
    // Whatever has not been heard yet, in the phone's voice.
    return speakOnDevice(pieces.slice(index).join(" "), lang);
  }
}

/**
 * Read an answer aloud. Resolves when it finishes, is stopped, or cannot start.
 *
 * Returns { ok, reason } rather than throwing: a missing voice is a normal
 * situation on a device that has never downloaded that language, and the caller
 * should tell the farmer, not crash.
 */
async function speakOnDevice(text, lang) {
  if (!SUPPORTED) return { ok: false, reason: "This browser cannot read text aloud." };
  if (!text) return { ok: false, reason: "Nothing to read." };
  const mine = session;

  const voices = await loadVoices();
  const voice = voiceFor(voices, lang);
  if (!voice) {
    return {
      ok: false,
      reason: `No ${lang} voice is installed on this device, so the answer cannot be read aloud.`,
    };
  }

  if (mine !== session) return { ok: true };
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang || lang;
    // Advice about a dose is worth slowing down for.
    utterance.rate = 0.95;
    utterance.onend = () => resolve({ ok: true });
    utterance.onerror = (e) => {
      // "interrupted" is what cancel() raises when the farmer presses stop, or
      // starts a second answer playing. That is not a failure to report.
      if (e.error === "interrupted" || e.error === "canceled") return resolve({ ok: true });
      resolve({ ok: false, reason: `Could not read the answer aloud (${e.error}).` });
    };
    window.speechSynthesis.speak(utterance);
  });
}
