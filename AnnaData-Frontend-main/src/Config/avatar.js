/**
 * Ankur, the voice companion, in its regional looks. Assam is the default;
 * a farmer will be able to pick another later (the choice is kept on this
 * phone). The pictures are 512 px WebP in public/avatars, 12-19 KB each.
 */
export const AVATARS = [
  { id: "assam", region: "Assam", look: "Jaapi hat and gamosa" },
  { id: "bengal", region: "Bengal", look: "Red-white checked gamcha" },
  { id: "punjab", region: "Punjab", look: "Saffron pagdi" },
  { id: "rajasthan", region: "Rajasthan", look: "Red bandhej safa" },
  { id: "maharashtra", region: "Maharashtra", look: "White Gandhi topi" },
  { id: "tamil", region: "Tamil Nadu", look: "White thundu" },
  { id: "up", region: "UP and Bihar", look: "Green saree pallu" },
].map((a) => ({ ...a, src: `${process.env.PUBLIC_URL || ""}/avatars/ankur-${a.id}.webp` }));

// Looks drawn in every voice-mode pose. The rest show their one picture and
// move it instead. Every pose is framed identically (checked: the hat sits on
// the same pixel in all of them), so swapping pictures never makes Ankur jump.
const POSED = ["assam"];
const POSES = ["listen", "think", "talk-open", "talk-half"];

/** The pictures for each voice-mode moment, or null for a single-picture look. */
export function posesOf(avatar) {
  if (!POSED.includes(avatar.id)) return null;
  const at = (pose) => `${process.env.PUBLIC_URL || ""}/avatars/ankur-${avatar.id}-${pose}.webp`;
  return { hello: avatar.src, ...Object.fromEntries(POSES.map((p) => [p, at(p)])) };
}

export const DEFAULT_AVATAR = "assam";
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
