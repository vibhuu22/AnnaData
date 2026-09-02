import { createContext, useCallback, useState } from "react";
import { ask } from "../Config/Gemini";

export const Context = createContext();

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
  replyLanguage: "en-IN",
  // A farmer who spoke their question is told the answer, not shown it. This
  // is what marks the turn as one to read aloud when it arrives.
  spoken: Boolean(audio),
  pending: true,
  failed: false,
});

const ContextProvider = (props) => {
  const [input, setInput] = useState("");
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
      .filter((item) => item.response && !item.failed)
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
              replyLanguage: result.replyLanguage,
              pending: false,
              failed: Boolean(result.error),
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
  };

  return (
    <Context.Provider value={contextValue}>{props.children}</Context.Provider>
  );
};

export default ContextProvider;
