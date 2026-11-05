import { getApiUrl } from "./api";
import { askHeaders, getToken, reportUnauthorized } from "./session";

const GEOLOCATION_TIMEOUT_MS = 3000;

/**
 * The phone's coordinates, if the farmer has already allowed it. Resolves to
 * null rather than rejecting, so location never blocks a question - the
 * backend answers without it and asks for a district, which the web shows
 * under the answer with a "Use my location" button.
 *
 * Never PROMPTS from here. This used to ask on every question and wait up to
 * eight seconds for the farmer to answer the permission dialog, so the first
 * question from a new visitor sat behind a popup they had not expected. Where
 * permission is already granted the position comes back at once from the
 * browser's cache.
 */
async function getCoordinates() {
  if (!("geolocation" in navigator)) return null;
  try {
    if (navigator.permissions?.query) {
      const status = await navigator.permissions.query({ name: "geolocation" });
      if (status.state !== "granted") return null;
    }
  } catch (e) {
    /* no Permissions API: try, briefly */
  }
  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false,
        timeout: GEOLOCATION_TIMEOUT_MS,
        maximumAge: 300000,
      });
    });
    return {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
    };
  } catch (error) {
    console.warn("Geolocation unavailable, proceeding without it:", error.message);
    return null;
  }
}

/**
 * The file name for a recording, from what the browser actually recorded.
 * Chrome records WebM, iPhone Safari MP4. Calling every recording voice.webm
 * mislabelled every iPhone voice note.
 */
function audioExtension(type) {
  const base = String(type || "").split(";")[0].trim().toLowerCase();
  if (base === "audio/mp4" || base === "audio/x-m4a" || base === "audio/aac") return ".m4a";
  if (base === "audio/ogg") return ".ogg";
  if (base === "audio/mpeg") return ".mp3";
  if (base === "audio/wav" || base === "audio/x-wav") return ".wav";
  return ".webm";
}

/** The backend returns a real status code with a {detail} body. Surface it. */
async function errorFrom(response) {
  let detail = response.statusText;
  try {
    const body = await response.json();
    detail = body.detail || body.error || detail;
  } catch (e) {
    /* non-JSON error body */
  }
  return new Error(`API error ${response.status}: ${detail}`);
}

/**
 * Read a streamed answer: newline-separated JSON events, as they arrive.
 * Returns the `done` event's fields, which are exactly what /agent returns.
 */
async function readEvents(response, { onHeard, onText }) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = null;
  const handle = (line) => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "heard") onHeard?.(event.transcript || "", event.vision || null);
    else if (event.type === "text") onText?.(event.text || "");
    else if (event.type === "done") done = event;
    else if (event.type === "error") {
      throw new Error(`API error ${event.status || 502}: ${event.detail || "the answer failed"}`);
    }
  };
  for (;;) {
    const { value, done: finished } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !finished });
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      handle(buffer.slice(0, newline));
      buffer = buffer.slice(newline + 1);
    }
    if (finished) break;
  }
  handle(buffer);
  if (!done) throw new Error("The answer was cut off. Please try again.");
  return done;
}

/**
 * Ask the agent one question, with an optional photo and voice note.
 *
 * Media goes to /agent/media as multipart in a single round trip.
 *
 * STREAMED WHERE IT CAN BE. With `onText`, the question goes to the /stream
 * form of the endpoint and each checked sentence of the answer is handed to
 * onText as it is written - the screen fills in, and voice mode starts
 * speaking, while the rest is still being written. `onHeard` receives what the
 * microphone was heard to say as soon as it is known. A backend without the
 * stream endpoints (404) is asked the ordinary way, so the two can be deployed
 * in either order.
 *
 * Always resolves. A failure comes back as { answer, error } so the caller can
 * render it as a message rather than having to catch.
 */
export async function ask({ text = "", history = [], image = null, audio = null, channel = "web", onHeard, onText }) {
  const coords = await getCoordinates();
  const hasMedia = Boolean(image || audio);
  const canStream = Boolean(onText) && typeof ReadableStream !== "undefined" && typeof TextDecoder !== "undefined";

  const send = (streamed) => {
    const suffix = streamed ? "/stream" : "";
    if (hasMedia) {
      const form = new FormData();
      if (image) form.append("image", image, image.name || "photo.jpg");
      // A recording is a Blob with no name; without one some servers reject the
      // part, and the extension is how the model is told what it is decoding.
      if (audio) form.append("audio", audio, audio.name || `voice${audioExtension(audio.type)}`);
      form.append("query", text);
      form.append("history", JSON.stringify(history));
      // "voice": a short spoken answer for voice mode, not a page of markdown.
      form.append("channel", channel);
      if (coords) {
        form.append("latitude", String(coords.latitude));
        form.append("longitude", String(coords.longitude));
      }
      // No Content-Type header: the browser sets it with the multipart boundary.
      return fetch(`${getApiUrl()}/agent/media${suffix}`, { method: "POST", headers: askHeaders(), body: form });
    }
    const body = { query: text, history, channel };
    if (coords) {
      body.latitude = coords.latitude;
      body.longitude = coords.longitude;
    }
    return fetch(`${getApiUrl()}/agent${suffix}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...askHeaders() },
      body: JSON.stringify(body),
    });
  };

  try {
    let streamed = canStream;
    let response = await send(streamed);
    if (streamed && (response.status === 404 || response.status === 405 || !response.body)) {
      streamed = false;
      response = await send(false);
    }

    // A token that stopped working mid-conversation. Reported so the app can
    // return the farmer to the sign-in screen, rather than leaving them on a
    // chat where every question comes back as an error.
    if (response.status === 401) reportUnauthorized();

    // A farmer who has not signed in and has reached the guest limit. Not an
    // error in their eyes and not shown as one: the backend's words say what to
    // do next, and needsSignIn lets the screen offer the way to do it.
    if (response.status === 429 && !getToken()) {
      let detail = "Confirm your phone number to keep asking.";
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (e) {
        /* keep the default */
      }
      return {
        answer: detail,
        transcript: "",
        vision: null,
        queryUsed: text,
        toolsUsed: [],
        doseStatus: null,
        replyLanguage: "en-IN",
        needsSignIn: true,
        error: new Error(detail),
      };
    }

    if (!response.ok) throw await errorFrom(response);

    const data = streamed ? await readEvents(response, { onHeard, onText }) : await response.json();
    if (typeof data.answer !== "string" || !data.answer.trim()) {
      throw new Error("The service returned an empty answer. Please try again.");
    }
    return {
      answer: data.answer || "No response from agent.",
      transcript: data.transcript || "",
      vision: data.vision || null,
      queryUsed: data.query_used || text,
      toolsUsed: data.tools_used || [],
      // "available", "none_registered" or "not_applicable". The one reliable
      // way to know an answer declined to name a dose: tools_used says "doses"
      // either way, because the register was consulted in both cases and simply
      // came back empty. null on a backend too old to send it, and the answer
      // surface falls back to reading the prose.
      doseStatus: data.dose_status || null,
      // What the answer still needs from the farmer, exactly as SMS gets it:
      // the bridge turns these into "Reply with your crop name..." on the
      // end of the text; the web shows the same ask under the answer.
      missingSlots: data.missing_slots || [],
      needsLocation: Boolean(data.needs_location),
      // The backend decides this from the script the answer is actually in, so
      // the browser never has to guess which voice to read it with.
      replyLanguage: data.reply_language || "en-IN",
      streamed,
      error: null,
    };
  } catch (error) {
    console.error("Error calling agent API:", error);
    return {
      answer: `Sorry, could not reach the AnnaData service. (${error.message})`,
      transcript: "",
      vision: null,
      queryUsed: text,
      toolsUsed: [],
      doseStatus: null,
      replyLanguage: "en-IN",
      error,
    };
  }
}

/** Text-only form, kept for callers that only want the answer string. */
async function run(prompt, history) {
  const { answer } = await ask({ text: prompt, history });
  return answer;
}

export default run;
