import { getApiUrl } from "./api";

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
      if (audio) form.append("audio", audio, audio.name || "voice.webm");
      form.append("query", text);
      form.append("history", JSON.stringify(history));
      if (coords) {
        form.append("latitude", String(coords.latitude));
        form.append("longitude", String(coords.longitude));
      }
      // No Content-Type header: the browser sets it with the multipart boundary.
      response = await fetch(`${getApiUrl()}/agent/media`, { method: "POST", body: form });
    } else {
      const body = { query: text, history };
      if (coords) {
        body.latitude = coords.latitude;
        body.longitude = coords.longitude;
      }
      response = await fetch(`${getApiUrl()}/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }

    if (!response.ok) throw await errorFrom(response);

    const data = await response.json();
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
