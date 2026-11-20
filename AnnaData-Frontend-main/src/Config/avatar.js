import { useSyncExternalStore } from "react";

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

// Looks with an idle animation (transparent WebM, framed like the still hello;
// tools/prepare_ankur_idle.py). The still stays where it cannot play.
const IDLE = ["bengal"];

/** The look's idle animation, or null. */
export function idleOf(avatar) {
  return IDLE.includes(avatar.id) ? `${process.env.PUBLIC_URL || ""}/avatars/ankur-${avatar.id}-idle.webm` : null;
}

/**
 * Whether to play an idle animation here: not when the farmer asked for less
 * motion or less data, and only where transparent WebM plays. Safari decodes
 * VP9 but drops its transparency, which would put a black box behind Ankur.
 */
export function canPlayIdle() {
  try {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return false;
    if (navigator.connection?.saveData) return false;
    const ua = navigator.userAgent || "";
    if (/^((?!chrome|chromium|android|crios|fxios|edg).)*safari/i.test(ua)) return false;
    return Boolean(document.createElement("video").canPlayType?.('video/webm; codecs="vp9"'));
  } catch (e) {
    return false;
  }
}

/** The pictures for each voice-mode moment, or null for a single-picture look. */
export function posesOf(avatar) {
  const poses = POSED[avatar.id];
  if (!poses) return null;
  const at = (pose) => `${process.env.PUBLIC_URL || ""}/avatars/ankur-${avatar.id}-${pose}.webp`;
  return { hello: avatar.src, ...Object.fromEntries(poses.map((p) => [p, at(p)])) };
}

export const DEFAULT_AVATAR = "master";
const KEY = "annadata.avatar";
const listeners = new Set();
let visitChoice = null; // the pick, when this phone's storage is blocked

/**
 * The looks a farmer can pick: those drawn in all six poses on a clear
 * background. Assam's earlier renders have only four, on a cream backdrop, so
 * it waits until it is redrawn like Bengal.
 */
export function pickableAvatars() {
  return AVATARS.filter((a) => POSED[a.id]?.length === ALL.length);
}

/** The look this phone shows: the farmer's choice, else the default. */
export function currentAvatar() {
  let id = DEFAULT_AVATAR;
  try {
    id = window.localStorage.getItem(KEY) || visitChoice || DEFAULT_AVATAR;
  } catch (e) {
    id = visitChoice || DEFAULT_AVATAR; // storage blocked
  }
  return pickableAvatars().find((a) => a.id === id) || AVATARS[0];
}

export function chooseAvatar(id) {
  visitChoice = id;
  try {
    window.localStorage.setItem(KEY, id);
  } catch (e) {
    /* remembered for this visit only */
  }
  listeners.forEach((listener) => listener());
}

const subscribe = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/** The current look, re-rendering wherever Ankur shows when a new one is picked. */
export function useAvatar() {
  const id = useSyncExternalStore(subscribe, () => currentAvatar().id, () => DEFAULT_AVATAR);
  return AVATARS.find((a) => a.id === id);
}
