/**
 * Ankur, the voice companion, in its regional looks. Master Ankur is the default;
 * a farmer will be able to pick another later (the choice is kept on this
 * phone). WebP assets share a 512 px canvas. Master expressions come from the
 * founder's 2048 px renders; see docs/mascot/clean-poses/README.md.
 */
export const AVATARS = [
  { id: "master", region: "Master Ankur", look: "The essential seed" },
  { id: "assam", region: "Assam", look: "Jaapi hat and gamosa" },
  { id: "bengal", region: "Bengal", look: "Red-white checked gamcha" },
  { id: "punjab", region: "Punjab", look: "Saffron pagdi" },
  { id: "rajasthan", region: "Rajasthan", look: "Red bandhej safa" },
  { id: "maharashtra", region: "Maharashtra", look: "White Gandhi topi" },
  { id: "tamil", region: "Tamil Nadu", look: "White thundu" },
  { id: "up", region: "UP and Bihar", look: "Green saree pallu" },
].map((a) => ({ ...a, src: `${process.env.PUBLIC_URL || ""}/avatars/ankur-${a.id}.webp` }));

// The voice-mode poses each look is drawn in; a look not listed shows its one
// picture and moves it instead. Every posed look shares Master Ankur's canvas,
// scale and baseline (tools/prepare_ankur_look.py), so poses swap in place.
const ALL = ["listen", "think", "talk-open", "talk-half", "sorry", "success"];
const POSED = {
  master: ALL,
  assam: ["listen", "think", "talk-open", "talk-half"],
  bengal: ALL,
};

/** The pictures for each voice-mode moment, or null for a single-picture look. */
export function posesOf(avatar) {
  const poses = POSED[avatar.id];
  if (!poses) return null;
  const at = (pose) => `${process.env.PUBLIC_URL || ""}/avatars/ankur-${avatar.id}-${pose}.webp`;
  return { hello: avatar.src, ...Object.fromEntries(poses.map((p) => [p, at(p)])) };
}

export const DEFAULT_AVATAR = "master";
const KEY = "annadata.avatar";

/** The look this phone shows: the farmer's choice, else the default. */
export function currentAvatar() {
  let id = DEFAULT_AVATAR;
  try {
    id = window.localStorage.getItem(KEY) || DEFAULT_AVATAR;
  } catch (e) {
    /* storage blocked: the default */
  }
  return AVATARS.find((a) => a.id === id) || AVATARS[0];
}

export function chooseAvatar(id) {
  try {
    window.localStorage.setItem(KEY, id);
  } catch (e) {
    /* remembered for this visit only */
  }
}
