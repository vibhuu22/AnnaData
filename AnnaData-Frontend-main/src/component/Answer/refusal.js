/**
 * Finding the refusal in an answer.
 *
 * The backend declines to name a chemical or a dose when the crop-pest pair is
 * not in the CIB&RC register, and sends the farmer to a Krishi Vigyan Kendra
 * instead. That refusal is the most trustworthy thing this product does, and it
 * arrives as an unremarkable middle paragraph, indistinguishable from advice.
 * This is how the interface finds it, so it can be shown as what it is.
 *
 * It has to be read out of the text, because there is no flag for it. The
 * `tools_used` array says `doses` either way - the register was consulted in
 * both cases, it simply came back empty. A boolean from the backend would be
 * the better fix by a distance and is worth asking for; this is the
 * frontend-only version, and its limits are set out below.
 *
 * TWO LEVELS, and it matters which is which.
 *
 * The whole answer is tested first, for all three signals: registration is
 * being discussed, something is being negated, and the farmer is being sent to
 * an extension officer. Any one or two of those turn up in ordinary advice; all
 * three together is the refusal and nothing else looks like it.
 *
 * Only if that passes is each paragraph tested, for the first two signals. This
 * split exists because the model does not paragraph consistently: a Hindi reply
 * puts the refusal and the referral in one paragraph, while the English reply
 * to the same question splits them across two. Requiring all three signals per
 * paragraph missed the English one entirely.
 *
 * WHAT IT DOES NOT DO. Every pattern below was taken from a reply the running
 * backend actually produced in Latin, Devanagari or Gurmukhi. Bengali is
 * included from the same vocabulary but has NOT been seen in a real refusal, so
 * treat it as untested. A miss is harmless - the paragraph renders as ordinary
 * prose, which is what it did before this file existed. A false positive is
 * also safe in the only direction that counts: it would make an answer look
 * less certain than it is, never more.
 */

// "registered", in each script as the model actually writes it. A Hindi refusal
// says "पंजीकृत कीटनाशक (registered pesticide)"; a Punjabi one, "ਰਜਿਸਟਰਡ".
const REGISTRATION =
  /register|पंजीकृत|पंजीकरण|रजिस्टर|ਰਜਿਸਟਰ|ਪੰਜੀਕ੍ਰਿਤ|ਸੂਚੀਬੱਧ|নিবন্ধিত|রেজিস্টার/i;

// A negation. Devanagari and Gurmukhi put it at the end of the clause.
//
// "absence of" was here and has been removed. It caught a second paragraph in
// the English reply - "In the absence of a registered chemical, you can take
// the following steps" - which is the handover to cultural controls, not the
// refusal. Two highlighted blocks in one answer is one too many; the point of
// the highlight is that there is exactly one thing to look at.
const NEGATION =
  /\bno\b|\bnot\b|\bnone\b|cannot|can't|unable|नहीं|असमर्थ|ਨਹੀਂ|ਅਸਮਰੱਥ|নেই|পারি না/i;

// Where the farmer is sent instead. KVK survives untranslated in every script
// the agent has been seen to answer in, because it is a proper noun.
const REFERRAL =
  /\bKVK\b|Krishi Vigyan Kendra|कृषि विज्ञान केंद्र|ਕ੍ਰਿਸ਼ੀ ਵਿਗਿਆਨ ਕੇਂਦਰ|কৃষি বিজ্ঞান কেন্দ্র|agricultur(?:e|al) officer|कृषि अधिकारी|ਖੇਤੀਬਾੜੀ ਅਫ਼ਸਰ|কৃষি অফিসার/i;

/** Does this answer, taken whole, decline to name a registered dose? */
export function answerDeclinesRegisteredDose(answer) {
  if (!answer || typeof answer !== "string") return false;
  return (
    REGISTRATION.test(answer) && NEGATION.test(answer) && REFERRAL.test(answer)
  );
}

/**
 * Within such an answer, is this the paragraph that carries the refusal?
 * Only meaningful once answerDeclinesRegisteredDose has said yes.
 */
export function paragraphCarriesRefusal(text) {
  if (!text || typeof text !== "string") return false;
  return REGISTRATION.test(text) && NEGATION.test(text);
}

export default answerDeclinesRegisteredDose;
