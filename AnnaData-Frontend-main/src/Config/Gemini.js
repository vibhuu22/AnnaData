import { getApiUrl } from "./api";
import { askHeaders, getToken, reportUnauthorized } from "./session";

const GEOLOCATION_TIMEOUT_MS = 8000;

/**
 * Ask the browser for coordinates. Resolves to null rather than rejecting, so a
 * denied or unavailable location never blocks the request - the backend simply
 * answers without location context.
 */
async function getCoordinates() {
  if (!("geolocation" in navigator)) {
    console.warn("Geolocation is not supported by this browser.");
    return null;
  }

  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
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
 * Ask the agent one question, with an optional photo and voice note.
 *
 * Media goes to /agent/media as multipart in a single round trip. The previous
 * version described the media at one endpoint, spliced the description into the
 * text box as a parenthetical, and posted that to /agent - two sequential waits,
 * and a structured reading of the photograph flattened into prose.
 *
 * Always resolves. A failure comes back as { answer, error } so the caller can
 * render it as a message rather than having to catch.
 */
export async function ask({ text = "", history = [], image = null, audio = null }) {
  const coords = await getCoordinates();
  const hasMedia = Boolean(image || audio);

  try {
    let response;

    if (hasMedia) {
      const form = new FormData();
      if (image) form.append("image", image, image.name || "photo.jpg");
      // A recording is a Blob with no name; without one some servers reject the
      // part, and the extension is how the model is told what it is decoding.
      if (audio) form.append("audio", audio, audio.name || `voice${audioExtension(audio.type)}`);
      form.append("query", text);
      form.append("history", JSON.stringify(history));
      if (coords) {
        form.append("latitude", String(coords.latitude));
        form.append("longitude", String(coords.longitude));
      }
      // No Content-Type header: the browser sets it with the multipart boundary.
      response = await fetch(`${getApiUrl()}/agent/media`, {
        method: "POST",
        headers: askHeaders(),
        body: form,
      });
    } else {
      const body = { query: text, history };
      if (coords) {
        body.latitude = coords.latitude;
        body.longitude = coords.longitude;
      }
      response = await fetch(`${getApiUrl()}/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...askHeaders() },
        body: JSON.stringify(body),
      });
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

    const data = await response.json();
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
      // The backend decides this from the script the answer is actually in, so
      // the browser never has to guess which voice to read it with.
      replyLanguage: data.reply_language || "en-IN",
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
