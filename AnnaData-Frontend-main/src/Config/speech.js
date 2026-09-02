/**
 * Reading an answer aloud, in the farmer's own language.
 *
 * A farmer who sends a voice note rather than typing often cannot comfortably
 * read the reply either, so an answer they can only read is half a feature.
 * This uses the browser's own speech synthesis: no API key, no per-request
 * cost, and it works on the Android Chrome that a farmer with a smartphone
 * actually has.
 *
 * Which voices exist is entirely up to the device. Where the language is
 * missing we say so rather than reading Devanagari with an English voice, which
 * produces sounds no one can follow.
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

export function isSpeechSupported() {
  return SUPPORTED;
}

export function stopSpeaking() {
  if (SUPPORTED) window.speechSynthesis.cancel();
}

/**
 * Read an answer aloud. Resolves when it finishes, is stopped, or cannot start.
 *
 * Returns { ok, reason } rather than throwing: a missing voice is a normal
 * situation on a device that has never downloaded that language, and the caller
 * should tell the farmer, not crash.
 */
export async function speak(markdown, lang) {
  if (!SUPPORTED) return { ok: false, reason: "This browser cannot read text aloud." };

  const text = speakableText(markdown);
  if (!text) return { ok: false, reason: "Nothing to read." };

  stopSpeaking();

  const voices = await loadVoices();
  const voice = voiceFor(voices, lang);
  if (!voice) {
    return {
      ok: false,
      reason: `No ${lang} voice is installed on this device, so the answer cannot be read aloud.`,
    };
  }

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
