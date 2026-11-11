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
