import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ask } from "../Config/Gemini";
import { fetchHistory } from "../Config/session";
import { Auth } from "./AuthProvider";

export const Context = createContext();

/**
 * The stored message log, folded back into turns.
 *
 * The backend keeps messages, not turns: a flat list of inbound and outbound
 * rows in time order, because that is what the SMS channel produces and both
 * channels write to the same table. The browser shows turns, so each inbound is
 * paired with the outbound that followed it.
 *
 * An inbound with no reply after it - the farmer asked, the service failed, or
 * an answer is still in flight from another device - is kept and shown with an
 * empty answer rather than dropped. Silently losing a farmer's question from
 * their own history would be worse than showing that it went unanswered.
 */
function foldIntoTurns(messages) {
  const turns = [];
  let current = null;

  messages.forEach((message, index) => {
    if (message.direction === "inbound") {
      if (current) turns.push(current);
      current = {
        id: `history-${index}`,
        prompt: message.body,
        response: "",
        mediaFile: null,
        mediaKind: null,
        transcript: "",
        vision: null,
        toolsUsed: [],
        doseStatus: null,
        replyLanguage: "en-IN",
        spoken: false,
        pending: false,
        failed: false,
        at: message.at,
      };
    } else if (current) {
      current.response = message.body;
      current.toolsUsed = message.meta?.tools || [];
      // Stored with the reply since dose_status was added to message meta, so a
      // past answer that declined to name a dose still says why after a reload.
      current.doseStatus = message.meta?.dose_status || null;
      turns.push(current);
      current = null;
    }
  });

  if (current) turns.push(current);
  return turns;
}

/**
 * One turn of the conversation, as the UI stores it.
 *
 * `pending` is what replaced the old two-entry flow: a media message used to
 * push a bubble reading "Understanding Image/Audio files...." and then append a
 * second entry for the answer, leaving the first one on screen forever. The
 * entry is now created once and filled in when the answer arrives.
 */
const newTurn = ({ text, image, audio }) => ({
  prompt: text,
  response: "",
  mediaFile: image || audio || null,
  mediaKind: image ? "image" : audio ? "audio" : null,
  transcript: "",
  vision: null,
  doseStatus: null,
  replyLanguage: "en-IN",
  // A farmer who spoke their question is told the answer, not shown it. This
  // is what marks the turn as one to read aloud when it arrives.
  spoken: Boolean(audio),
  pending: true,
  failed: false,
  needsSignIn: false,
});

const ContextProvider = (props) => {
  const { user } = useContext(Auth);
  const [input, setInput] = useState("");
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [recentPrompt, setRecentPrompt] = useState("");
  const [previousPrompt, setPreviousPrompt] = useState([]);
  const [showResult, setShowResult] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resultData, setResultData] = useState("");
  const [responses, setResponses] = useState([]);
  const [dataSent, setDataSent] = useState(false);

  const resetChat = () => {
    setResponses([]);
    setDataSent(false);
    setShowResult(false);
    setResultData("");
    setRecentPrompt("");
  };

  /**
   * Load this farmer's past conversation, or throw it away when they sign out.
   *
   * Keyed on user_id rather than on truthiness, so signing in as a different
   * farmer on the same phone replaces the conversation instead of appending to
   * somebody else's.
   */
  const userId = user?.user_id || null;
  useEffect(() => {
    let cancelled = false;

    if (!userId) {
      // A guest, or a farmer who just signed out. A sign-out must not leave
      // the previous farmer's conversation on a shared phone.
      setResponses([]);
      setDataSent(false);
      setHistoryLoaded(true);
      return undefined;
    }

    setHistoryLoaded(false);
    (async () => {
      try {
        const data = await fetchHistory(50);
        if (cancelled) return;
        const turns = foldIntoTurns(data.messages || []);
        // A guest who has just signed in had their questions moved onto this
        // number by the backend, so the stored history already holds them.
        // If it came back empty anyway (an older backend that does not move
        // them), keep what is on screen rather than blanking the conversation
        // the farmer is in the middle of.
        if (turns.length === 0) return;
        setResponses(turns);
        // Straight to the conversation when there is one; a returning farmer
        // should see what they asked last time, not the empty landing screen.
        setDataSent(turns.length > 0);
      } catch (e) {
        // History is a convenience. Failing to load it must not stop a farmer
        // asking a new question, so this is a warning and not an error state.
        console.warn("Could not load past conversation:", e.message);
      } finally {
        if (!cancelled) setHistoryLoaded(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  /**
   * Send one message: text, a photo, a voice note, or any combination.
   *
   * History is built from the turns already on screen. Only turns that actually
   * got an answer are included - a failed request must not teach the agent that
   * it said "could not reach the service".
   */
  const send = useCallback(async ({ text = "", image = null, audio = null }) => {
    const trimmed = text.trim();
    if (!trimmed && !image && !audio) return;

    // Matched by id rather than by position: the answer arrives seconds later,
    // by which time the farmer may have sent another message and shifted every
    // index after this one.
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setResponses((prev) => [...prev, { ...newTurn({ text: trimmed, image, audio }), id }]);

    const history = responses
      .filter((item) => item.response && !item.failed && !item.needsSignIn)
      .flatMap((item) => [
        { role: "user", content: item.transcript || item.prompt },
        { role: "assistant", content: item.response },
      ]);

    setDataSent(true);
    setLoading(true);
    setShowResult(true);
    setRecentPrompt(trimmed);
    if (trimmed) setPreviousPrompt((prev) => [...prev, trimmed]);
    setInput("");

    const result = await ask({ text: trimmed, history, image, audio });

    setResponses((prev) =>
      prev.map((item) =>
        item.id !== id
          ? item
          : {
              ...item,
              response: result.answer,
              // What the microphone heard, shown back so the farmer can catch a
              // misheard word rather than wondering why the answer is odd.
              transcript: result.transcript,
              vision: result.vision,
              toolsUsed: result.toolsUsed,
              doseStatus: result.doseStatus,
              replyLanguage: result.replyLanguage,
              pending: false,
              // A guest who reached the question limit. Not a failure: the
              // answer surface offers sign-in instead of showing an error.
              needsSignIn: Boolean(result.needsSignIn),
              failed: Boolean(result.error) && !result.needsSignIn,
            }
      )
    );
    setResultData(result.answer);
    setLoading(false);
  }, [responses]);

  /** Text-only send, for the callers that still pass through `input`. */
  const onSent = useCallback(() => send({ text: input }), [send, input]);

  const contextValue = {
    previousPrompt,
    setPreviousPrompt,
    send,
    onSent,
    setRecentPrompt,
    recentPrompt,
    showResult,
    loading,
    resultData,
    responses,
    setResponses,
    setLoading,
    input,
    setInput,
    resetChat,
    dataSent,
    setDataSent,
    historyLoaded,
  };

  return (
    <Context.Provider value={contextValue}>{props.children}</Context.Provider>
  );
};

export default ContextProvider;
