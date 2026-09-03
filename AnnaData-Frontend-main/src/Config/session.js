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
  const data = await apiFetch("/auth/verify", {
    method: "POST",
    body: { phone, code },
  });
  setToken(data.token);
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

export async function signOut() {
  try {
    await apiFetch("/auth/signout", { method: "POST" });
  } catch (e) {
    // Signing out locally must succeed even if the server cannot be reached.
    console.warn("Could not sign out on the server:", e.message);
  }
  clearToken();
}
