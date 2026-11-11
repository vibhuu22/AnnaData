/**
 * Ankur, the voice companion, in its regional looks. Master Ankur is the default;
 * a farmer will be able to pick another later (the choice is kept on this
 * phone). WebP assets share a 512 px canvas. Master expressions are sheet crops,
 * not native 512 px renders; see docs/mascot/astra-implementation.md.
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

// Looks drawn in every voice-mode pose. The rest show their one picture and
// move it instead. Master crops share torso anchors, a common canvas and baseline.
const POSED = ["master", "assam"];
const POSES = ["listen", "think", "talk-open", "talk-half"];

/** The pictures for each voice-mode moment, or null for a single-picture look. */
export function posesOf(avatar) {
  if (!POSED.includes(avatar.id)) return null;
  // The sheets contain different talking renders, not a registered mouth pair.
  // Hold one talking pose for Master rather than making its arms/body jump.
  const at = (pose) => `${process.env.PUBLIC_URL || ""}/avatars/ankur-${avatar.id}-${avatar.id === 'master' && pose === 'talk-half' ? 'talk-open' : pose}.webp`;
  return { hello: avatar.src, ...Object.fromEntries((avatar.id === "master" ? [...POSES, "sorry", "success"] : POSES).map((p) => [p, at(p)])) };
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
