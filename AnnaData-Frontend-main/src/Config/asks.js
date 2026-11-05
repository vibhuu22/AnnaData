/**
 * The one thing an answer still needs, asked the way SMS asks it - and in the
 * language the answer is in.
 *
 * The backend returns missing_slots and needs_location with every answer. The
 * SMS bridge has always turned the first of them into one line on the end of
 * the reply ("Reply with your crop name for specific advice."). The web shows
 * the same ask under the answer, and voice mode says it aloud after the
 * answer - which is why it cannot be in English when the farmer spoke Hindi.
 *
 * Same order as the bridge: a missing slot first, then location.
 *
 * The translations are plain and were written for this, not checked by a
 * native speaker of each language yet. They are short on purpose: a farmer
 * hears them after a full answer.
 */

const ASKS = {
  crop: {
    en: "Tell us your crop for advice specific to it.",
    hinglish: "Apni fasal ka naam bataiye, taaki salah aapki fasal ke hisaab se ho.",
    hi: "अपनी फ़सल का नाम बताइए, ताकि सलाह आपकी फ़सल के हिसाब से हो।",
    bn: "আপনার ফসলের নাম বলুন, যাতে পরামর্শ আপনার ফসল অনুযায়ী হয়।",
    pa: "ਆਪਣੀ ਫ਼ਸਲ ਦਾ ਨਾਮ ਦੱਸੋ, ਤਾਂ ਜੋ ਸਲਾਹ ਤੁਹਾਡੀ ਫ਼ਸਲ ਮੁਤਾਬਕ ਹੋਵੇ।",
  },
  location: {
    en: "Tell us your village or district for advice specific to your area.",
    hinglish: "Apna gaon ya zila bataiye, taaki salah aapke ilaake ke hisaab se ho.",
    hi: "अपना गाँव या ज़िला बताइए, ताकि सलाह आपके इलाक़े के हिसाब से हो।",
    bn: "আপনার গ্রাম বা জেলার নাম বলুন, যাতে পরামর্শ আপনার এলাকা অনুযায়ী হয়।",
    pa: "ਆਪਣਾ ਪਿੰਡ ਜਾਂ ਜ਼ਿਲ੍ਹਾ ਦੱਸੋ, ਤਾਂ ਜੋ ਸਲਾਹ ਤੁਹਾਡੇ ਇਲਾਕੇ ਮੁਤਾਬਕ ਹੋਵੇ।",
  },
  state: {
    en: "Tell us your state so we can check your local mandi prices.",
    hinglish: "Apna rajya bataiye, taaki hum aapki mandi ke bhav dekh sakein.",
    hi: "अपना राज्य बताइए, ताकि हम आपकी मंडी के भाव देख सकें।",
    bn: "আপনার রাজ্যের নাম বলুন, যাতে আমরা আপনার মান্ডির দাম দেখতে পারি।",
    pa: "ਆਪਣਾ ਸੂਬਾ ਦੱਸੋ, ਤਾਂ ਜੋ ਅਸੀਂ ਤੁਹਾਡੀ ਮੰਡੀ ਦੇ ਭਾਅ ਵੇਖ ਸਕੀਏ।",
  },
};

// Words that mark romanised Hindi. Two or more and the answer is Hinglish.
const HINGLISH = /\b(hai|hain|karein|kijiye|mein|aap|aapke|aapki|ke|ki|ka|nahi|ya|aur|fasal|dawa)\b/gi;

/** Which language an answer is in, as far as these asks need to know. */
export function answerLanguage(text) {
  const value = String(text || "");
  if (/[ঀ-৿]/.test(value)) return "bn";
  if (/[਀-੿]/.test(value)) return "pa";
  if (/[ऀ-ॿ]/.test(value.replace(/[।॥]/g, ""))) return "hi";
  return (value.match(HINGLISH) || []).length >= 2 ? "hinglish" : "en";
}

/** { slot, text } for the one thing this answer still needs, or null. */
export function followUpAsk(turn) {
  if (!turn) return null;
  const slot = (turn.missingSlots || []).find((s) => ASKS[s]) || (turn.needsLocation ? "location" : null);
  if (!slot) return null;
  return { slot, text: ASKS[slot][answerLanguage(turn.response || turn.answer)] };
}

/**
 * What voice mode says the moment a farmer stops talking, in the language of
 * the conversation so far. Only that the question was heard.
 */
const CUES = {
  hi: "जी, एक पल।",
  hinglish: "जी, एक पल।",
  bn: "জি, এক মুহূর্ত।",
  pa: "ਜੀ, ਇੱਕ ਪਲ।",
  en: "Okay, one moment.",
};

export function cueFor(language) {
  return CUES[language] || CUES.hi;
}
