import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
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
/**
 * Which chat a stored message belongs to. Web messages carry the chat id the
 * browser made; SMS messages have none and are grouped by session - a
 * conversation the backend counts as finished after a quiet gap - and failing
 * that, by day.
 */
function chatOf(message) {
  if (message.meta?.chat) return message.meta.chat;
  if (message.session) return `session-${message.session}`;
  return `day-${String(message.at || "").slice(0, 10) || "earlier"}`;
}

/** A fresh chat id: short, and only the characters the backend accepts. */
export function newChatId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * The chats, newest activity first: id, title (its first question), when it
 * last moved, and how many turns it has.
 */
export function chatsOf(turns) {
  const byId = new Map();
  turns.forEach((turn) => {
    const chat = byId.get(turn.chatId) || { id: turn.chatId, title: "", at: null, count: 0, order: 0 };
    if (!chat.title) chat.title = (turn.prompt || turn.transcript || "").trim();
    chat.at = turn.at || chat.at;
    chat.count += 1;
    chat.order = Math.max(chat.order, turns.indexOf(turn));
    byId.set(turn.chatId, chat);
  });
  return [...byId.values()]
    .map((chat) => ({ ...chat, title: chat.title || "Voice or photo question" }))
    .sort((a, b) => b.order - a.order);
}

function foldIntoTurns(messages) {
  const turns = [];
  let current = null;

  messages.forEach((message, index) => {
    if (message.direction === "inbound") {
      if (current) turns.push(current);
      current = {
        id: `history-${index}`,
        chatId: chatOf(message),
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
      // So an answer reopened from history can still be rated as itself.
      current.requestId = message.meta?.request_id || null;
      current.toolsUsed = message.meta?.tools || [];
      // Stored with the reply since dose_status was added to message meta, so a
      // past answer that declined to name a dose still says why after a reload.
      current.doseStatus = message.meta?.dose_status || null;
      current.diagnosis = message.meta?.diagnosis || null;
      current.missingSlots = message.meta?.missing || [];
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
const newTurn = ({ text, image, audio, quiet }) => ({
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
  // Voice mode reads its own answers, so it marks its turns quiet.
  spoken: Boolean(audio) && !quiet,
  pending: true,
  failed: false,
  needsSignIn: false,
  // Asked in this visit, so its answer is written out on screen; history
  // turns are shown at once.
  live: true,
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
  /*
   * Which screen the main area shows:
   *   ask      the empty "What is happening in your field?" screen
   *   chat     one conversation
   *   home     a returning farmer's welcome: their farm, recent chats
   *   explore  what AnnaData can help with
   *   news     farming news for their state
   *
   * CHATS, NOT ONE LONG THREAD. Each conversation is its own chat, as in
   * ChatGPT: "New chat" starts one, the sidebar lists them, and only the open
   * chat's turns are on screen or sent to the agent as context.
   */
  const [screen, setScreen] = useState("ask");
  // The menu: a panel on a wide screen (open by default), a drawer on a phone
  // (closed). Kept here rather than in the sidebar because on a phone it is
  // opened from the bottom bar's "More".
  const [menuOpen, setMenuOpen] = useState(
    () => typeof window !== "undefined" && window.innerWidth >= 1024
  );
  const [currentChatId, setCurrentChatId] = useState(null);
  const screenRef = useRef(screen);
  const chatRef = useRef(currentChatId);
  const responsesRef = useRef(responses);
  screenRef.current = screen;
  chatRef.current = currentChatId;
  responsesRef.current = responses;

  const newChat = useCallback(() => {
    // Set on the ref at once too, so a question sent straight after (from
    // Explore) lands in the new chat, not the one before it.
    const id = newChatId();
    chatRef.current = id;
    setCurrentChatId(id);
    setScreen("ask");
    setShowResult(false);
    setResultData("");
    setRecentPrompt("");
  }, []);

  /** Open one chat, scrolled to a turn in it if one is named. */
  const [focusId, setFocusId] = useState(null);
  const openChat = useCallback((chatId, turnId = null) => {
    setCurrentChatId(chatId);
    setScreen("chat");
    setFocusId(turnId);
  }, []);
  const openTurn = useCallback(
    (turnId) => {
      const turn = responses.find((t) => t.id === turnId);
      if (turn) openChat(turn.chatId, turnId);
    },
    [responses, openChat]
  );

  // Home is the welcome for a farmer with chats; for anyone else it is the
  // ask screen, which is the app's front door.
  const goHome = useCallback(() => {
    if (user && responses.length) setScreen("home");
    else newChat();
  }, [user, responses.length, newChat]);

  // Kept for older callers.
  const startNewQuestion = newChat;
  const resetChat = newChat;

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
      setCurrentChatId(null);
      setScreen("ask");
      setHistoryLoaded(true);
      return undefined;
    }

    setHistoryLoaded(false);
    (async () => {
      try {
        const data = await fetchHistory(200);
        if (cancelled) return;
        const turns = foldIntoTurns(data.messages || []);
        // A guest who has just signed in had their questions moved onto this
        // number by the backend, so the stored history already holds them.
        // If it came back empty anyway (an older backend that does not move
        // them), keep what is on screen rather than blanking the conversation
        // the farmer is in the middle of.
        if (turns.length === 0) return;
        // Signed in mid-chat, but the stored messages carry no chat id (a
        // backend from before chats): keep the turns that were on screen in
        // the open chat rather than letting the conversation vanish.
        const open = chatRef.current;
        if (screenRef.current === "chat" && open && !turns.some((t) => t.chatId === open)) {
          const onScreen = responsesRef.current.filter((t) => t.chatId === open).length;
          turns.slice(-onScreen).forEach((t) => {
            t.chatId = open;
          });
        }
        setResponses(turns);
        // Signed in from the middle of a chat (the guest's save flow): the
        // questions were stored with this chat's id and moved onto the number,
        // so the same chat is still open. Otherwise, a returning farmer is
        // welcomed with their chats.
        if (screenRef.current !== "chat" || !chatRef.current) setScreen("home");
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
  const send = useCallback(async ({ text = "", image = null, audio = null, quiet = false, channel = "web", onHeard, onText }) => {
    const trimmed = text.trim();
    if (!trimmed && !image && !audio) return null;

    // Matched by id rather than by position: the answer arrives seconds later,
    // by which time the farmer may have sent another message and shifted every
    // index after this one.
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const chatId = chatRef.current || newChatId();
    if (!chatRef.current) {
      chatRef.current = chatId;
      setCurrentChatId(chatId);
    }
    setResponses((prev) => [
      ...prev,
      { ...newTurn({ text: trimmed, image, audio, quiet }), id, chatId, startedAt: Date.now(), at: new Date().toISOString() },
    ]);

    // Only this chat is the agent's context, never the farmer's other chats.
    const history = responses
      .filter((item) => item.chatId === chatId)
      .filter((item) => item.response && !item.failed && !item.needsSignIn)
      .flatMap((item) => [
        { role: "user", content: item.transcript || item.prompt },
        { role: "assistant", content: item.response },
      ]);

    setScreen("chat");
    setLoading(true);
    setShowResult(true);
    setRecentPrompt(trimmed);
    if (trimmed) setPreviousPrompt((prev) => [...prev, trimmed]);
    setInput("");

    // The answer fills in as it is written: the first sentence replaces the
    // waiting indicator, and the rest follow. `streaming` marks a turn whose
    // text is still arriving, so the badge, Listen and rating wait for the
    // whole, checked answer.
    const update = (change) =>
      setResponses((prev) => prev.map((item) => (item.id === id ? { ...item, ...change(item) } : item)));
    const result = await ask({
      text: trimmed,
      history,
      image,
      audio,
      channel,
      chatId,
      onHeard: (transcript, vision) => {
        update(() => ({ transcript, vision }));
        onHeard?.(transcript, vision);
      },
      onText: (piece) => {
        update((item) => ({ response: (item.streaming ? item.response : "") + piece, pending: false, streaming: true }));
        onText?.(piece);
      },
    });

    setResponses((prev) =>
      prev.map((item) =>
        item.id !== id
          ? item
          : {
              ...item,
              // The authoritative answer, after every check on the whole of
              // it - which can add to what was streamed, never contradict it.
              response: result.answer,
              requestId: result.requestId || null,
              streaming: false,
              // What the microphone heard, shown back so the farmer can catch a
              // misheard word rather than wondering why the answer is odd.
              transcript: result.transcript,
              vision: result.vision,
              diagnosis: result.diagnosis,
              toolsUsed: result.toolsUsed,
              doseStatus: result.doseStatus,
              missingSlots: result.missingSlots || [],
              needsLocation: Boolean(result.needsLocation),
              confirmPlace: result.confirmPlace || null,
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
    // Handed back for voice mode, which reads the answer aloud itself.
    return { ...result, id };
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
    // The turns of the chat on screen, and every chat.
    thread: responses.filter((turn) => turn.chatId === currentChatId),
    chats: chatsOf(responses),
    currentChatId,
    newChat,
    openChat,
    screen,
    setScreen,
    menuOpen,
    setMenuOpen,
    startNewQuestion,
    openTurn,
    goHome,
    focusId,
    dataSent: screen !== "ask",
    historyLoaded,
  };

  return (
    <Context.Provider value={contextValue}>{props.children}</Context.Provider>
  );
};

export default ContextProvider;
