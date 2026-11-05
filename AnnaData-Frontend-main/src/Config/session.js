import { getApiUrl } from "./api";

/**
 * The signed-in farmer's session.
 *
 * The token lives in localStorage rather than in memory, because a farmer on a
 * phone will background this app constantly and being signed out every time
 * would mean another SMS from our own SIM to get back in. The known cost is that
 * script running on this page could read it - the usual argument for an
 * httpOnly cookie. A cookie was not chosen because the API is on a different
 * origin from the app, which puts a cookie into SameSite=None territory and
 * needs credentialed CORS on every request. Worth revisiting; not worth blocking
 * sign-in on.
 */
const TOKEN_KEY = "annadata.token";

let cachedToken = null;

export function getToken() {
  if (cachedToken !== null) return cachedToken;
  try {
    cachedToken = window.localStorage.getItem(TOKEN_KEY) || "";
  } catch (e) {
    // Private mode, or storage disabled. The session simply lasts one page.
    cachedToken = "";
  }
  return cachedToken;
}

export function setToken(token) {
  cachedToken = token || "";
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch (e) {
    /* nothing to do; the in-memory copy still works for this page */
  }
}

export function clearToken() {
  setToken("");
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Who this browser is before the farmer has signed in.
 *
 * A farmer now asks first and confirms their number only when they choose to
 * save their farm. Until then their questions are answered under a random id
 * this browser makes up and keeps. It proves nothing about who they are - the
 * backend treats it accordingly, answering within tight limits and never
 * touching a real farmer's profile with it - and its one job is to let the
 * questions asked before sign-in be moved onto the farmer's number afterwards.
 */
const GUEST_KEY = "annadata.guest";
let cachedGuest = null;

function newGuestId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  // A version-4 UUID by hand, for browsers without randomUUID. The backend
  // accepts only this exact shape, so it has to match it precisely.
  // The id is not a secret - it proves nothing and is only ever trusted
  // within guest limits - so where even getRandomValues is missing (very old
  // browsers, some test environments) Math.random is good enough.
  const bytes = new Uint8Array(16);
  if (window.crypto?.getRandomValues) window.crypto.getRandomValues(bytes);
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getGuestId() {
  if (cachedGuest) return cachedGuest;
  try {
    cachedGuest = window.localStorage.getItem(GUEST_KEY) || "";
  } catch (e) {
    cachedGuest = "";
  }
  if (!cachedGuest) {
    cachedGuest = newGuestId();
    try {
      window.localStorage.setItem(GUEST_KEY, cachedGuest);
    } catch (e) {
      /* lasts this page only */
    }
  }
  return cachedGuest;
}

/** A fresh guest id, so a farmer who signs out does not carry the old one. */
export function resetGuestId() {
  cachedGuest = null;
  try {
    window.localStorage.removeItem(GUEST_KEY);
  } catch (e) {
    /* nothing to do */
  }
}

/** Headers for a question: the farmer's token if they have one, else the guest id. */
export function askHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : { "X-Guest-Id": getGuestId() };
}

/**
 * Anyone can subscribe to "the token stopped working".
 *
 * A 401 can come back from any request, including one fired from deep inside
 * the chat. Rather than every caller knowing how to bounce the farmer to the
 * sign-in screen, they all report it here and the auth provider listens.
 */
const expiryListeners = new Set();

export function onSessionExpired(listener) {
  expiryListeners.add(listener);
  return () => expiryListeners.delete(listener);
}

/**
 * Exported because the chat does not go through apiFetch.
 *
 * `ask` in Gemini.js always resolves, so that a failure renders as a message
 * instead of throwing into the component tree. That means it cannot rely on
 * apiFetch's 401 handling and has to report one itself - otherwise a farmer
 * whose token expired mid-conversation sits on a chat screen where every
 * question comes back as an error, with no way to sign in again.
 */
export function reportUnauthorized() {
  if (!getToken()) return;
  clearToken();
  expiryListeners.forEach((listener) => {
    try {
      listener();
    } catch (e) {
      console.error("Session expiry listener failed:", e);
    }
  });
}

function sessionExpired() {
  reportUnauthorized();
}

/** The {detail} the backend sends with a real status code. */
async function detailFrom(response) {
  try {
    const body = await response.json();
    return body.detail || body.error || response.statusText;
  } catch (e) {
    return response.statusText;
  }
}

/**
 * fetch, with the token attached and a 401 handled once, centrally.
 *
 * Returns parsed JSON and throws an Error carrying `status` and `retryAfter`,
 * because the sign-in screen needs to tell a wrong code (401) from a cooldown
 * (429) and show a countdown for the second.
 */
export async function apiFetch(path, { method = "GET", body, headers = {} } = {}) {
  const isForm = body instanceof FormData;
  const response = await fetch(`${getApiUrl()}${path}`, {
    method,
    headers: {
      ...(isForm ? {} : body ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(),
      ...headers,
    },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401 && getToken()) {
    // A token we HELD was rejected: expired, or signed out elsewhere. A 401 with
    // no token is just an unauthenticated call and needs no announcement.
    sessionExpired();
  }

  if (!response.ok) {
    const error = new Error(await detailFrom(response));
    error.status = response.status;
    const retry = response.headers.get("Retry-After");
    error.retryAfter = retry ? parseInt(retry, 10) : 0;
    throw error;
  }

  if (response.status === 204) return null;
  return response.json();
}

// --- The sign-in flow -----------------------------------------------------

export function requestCode(phone) {
  return apiFetch("/auth/request-code", { method: "POST", body: { phone } });
}

export async function verifyCode(phone, code) {
  // The guest id goes with the code so the backend can move the questions
  // asked before sign-in onto this number. Then it is thrown away: it has done
  // its one job, and keeping it would let a later sign-out resurrect it.
  const data = await apiFetch("/auth/verify", {
    method: "POST",
    body: { phone, code, guest_id: getGuestId() },
  });
  setToken(data.token);
  resetGuestId();
  return data;
}

export function fetchMe() {
  return apiFetch("/auth/me");
}

export function saveProfile(profile) {
  return apiFetch("/profile", { method: "PUT", body: profile });
}

export function fetchHistory(limit = 50) {
  return apiFetch(`/history?limit=${encodeURIComponent(limit)}`);
}

/**
 * A thumbs up or down on the answer just given. Guests may rate too, under
 * their browser id, and the rating moves onto their number if they sign in.
 */
export async function rateAnswer(up, note = "") {
  const response = await fetch(`${getApiUrl()}/feedback/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...askHeaders() },
    body: JSON.stringify({ up, note: note || null }),
  });
  if (!response.ok) throw new Error(`rating ${response.status}`);
  return response.json();
}

/** The week's farming headlines for a state; the farmer's own when none is named. */
/**
 * News for a state. With `coords`, the state the phone is in wins whenever it
 * can be found; `state` is then only the fallback.
 */
export async function fetchNews(state = "", coords = null) {
  const params = new URLSearchParams();
  if (state) params.set("state", state);
  if (coords) {
    params.set("latitude", coords.latitude);
    params.set("longitude", coords.longitude);
  }
  const query = params.toString() ? `?${params}` : "";
  const response = await fetch(`${getApiUrl()}/news${query}`, { headers: authHeaders() });
  if (!response.ok) throw new Error(`news ${response.status}`);
  return response.json();
}

export async function signOut() {
  try {
    await apiFetch("/auth/signout", { method: "POST" });
  } catch (e) {
    // Signing out locally must succeed even if the server cannot be reached.
    console.warn("Could not sign out on the server:", e.message);
  }
  clearToken();
}
