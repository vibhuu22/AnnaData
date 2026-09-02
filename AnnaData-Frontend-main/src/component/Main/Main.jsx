import React, { useContext, useState, useRef, useEffect, useMemo, useCallback } from "react";
import { assets } from "../../assets/assets";
import Card from "../Card/Card";
import icon4 from "../../assets/message_icon.png";
import { IoMdSend } from "react-icons/io";
import { FaImage, FaMicrophone, FaStop, FaVolumeUp, FaRegStopCircle } from "react-icons/fa";
import { Context } from "../../Context/ContextProvider";
import Markdown from "markdown-to-jsx";
import MediaPreview from "../MediaPreview/MediaPreview";
import Sources from "../Sources/Sources";
import { speak, stopSpeaking, isSpeechSupported } from "../../Config/speech";

// Deliberately not all English. The system answers in the script it is asked
// in, and a demo that only ever shows English questions never demonstrates the
// one capability that distinguishes it. Each card carries its own translation
// so the behaviour is legible to someone who does not read the script.
const SUGGESTIONS = [
  {
    text: "मेरे गेहूं में पीला रतुआ लग गया है, क्या करूं?",
    note: "Hindi — yellow rust in wheat",
  },
  {
    text: "Kapas me sundi lag gayi hai, kaunsi dawa daalu?",
    note: "Hinglish — bollworm in cotton",
  },
  {
    text: "What is today's mandi price for soybean in Madhya Pradesh?",
    note: "English — live market rate",
  },
  {
    text: "ਮੇਰੇ ਝੋਨੇ ਨੂੰ ਕਦੋਂ ਪਾਣੀ ਦੇਣਾ ਚਾਹੀਦਾ ਹੈ?",
    note: "Punjabi — irrigation timing for paddy",
  },
];

/**
 * A blob rendered as an image or an audio player.
 *
 * The object URL is created once per file and revoked on unmount. The previous
 * version called URL.createObjectURL inline in the render, which minted a fresh
 * URL on every re-render and never released any of them.
 */
function SentMedia({ file, kind }) {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => url && URL.revokeObjectURL(url), [url]);
  if (!url) return null;
  return kind === "image" ? (
    <img src={url} alt="Sent by the farmer" className="max-h-44 rounded-lg" />
  ) : (
    <audio controls src={url} className="h-9" />
  );
}

function Main() {
  const { send, responses, loading, setInput, input, dataSent } = useContext(Context);

  const [selectedImage, setSelectedImage] = useState(null);
  const [selectedAudio, setSelectedAudio] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [micError, setMicError] = useState("");
  const [speakingId, setSpeakingId] = useState(null);
  const [speechError, setSpeechError] = useState("");

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const bottomRef = useRef(null);
  const autoSpokenRef = useRef(new Set());

  // Keep the newest turn in view as answers stream in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [responses, loading]);

  const readAloud = useCallback(async (turn) => {
    setSpeechError("");
    setSpeakingId(turn.id);
    const { ok, reason } = await speak(turn.response, turn.replyLanguage);
    if (!ok) setSpeechError(reason);
    setSpeakingId((current) => (current === turn.id ? null : current));
  }, []);

  const hush = () => {
    stopSpeaking();
    setSpeakingId(null);
  };

  // An answer to a spoken question is read back without being asked. A farmer
  // who recorded their question rather than typing it is usually not reading
  // the reply either. Tracked by id so a re-render never replays an answer.
  useEffect(() => {
    const turn = responses.find(
      (t) => t.spoken && !t.pending && !t.failed && !autoSpokenRef.current.has(t.id)
    );
    if (!turn) return;
    autoSpokenRef.current.add(turn.id);
    readAloud(turn);
  }, [responses, readAloud]);

  // Silence anything still playing when the farmer leaves the page.
  useEffect(() => () => stopSpeaking(), []);

  const clearSelectedImage = () => setSelectedImage(null);
  const clearSelectedAudio = () => setSelectedAudio(null);

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) setSelectedImage(file);
    // Reset the input so choosing the same file twice still fires onChange.
    e.target.value = "";
  };

  const handleAudioRecord = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    setMicError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        setSelectedAudio(new Blob(audioChunksRef.current, { type: "audio/webm" }));
        stream.getTracks().forEach((track) => track.stop());
      };
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      // A denied microphone used to fail silently to the console, so the button
      // simply did nothing and the farmer had no idea why.
      console.error("Error accessing microphone:", err);
      setMicError("Microphone unavailable. Check the browser's permission for this site.");
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (isRecording) {
      // Sending while still recording would attach nothing. Stop first.
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const image = selectedImage;
    const audio = selectedAudio;
    setSelectedImage(null);
    setSelectedAudio(null);
    await send({ text: input, image, audio });
  };

  const canSend = Boolean(input.trim() || selectedImage || selectedAudio);

  return (
    <div className="flex-grow min-h-0 w-full flex flex-col overflow-hidden">
      <div className="flex-grow flex flex-col relative overflow-hidden">
        <div className="bg-white flex flex-col w-full flex-grow overflow-y-auto p-4 items-center">
          {!dataSent ? (
            <div className="w-full flex-grow flex flex-col justify-center">
              <div className="mx-auto max-w-[900px] w-full">
                <p className="text-center text-lg text-gray-600">
                  Ask about your crop — type it, speak it, or send a photo.
                </p>
                <p className="text-center text-sm text-gray-400 mt-2">
                  Answers come back in the language you asked in, with doses taken
                  from the CIB&amp;RC register rather than invented.
                </p>
                <div className="mt-8 sm:mt-10 flex gap-4 overflow-x-auto scrollbar-hide md:grid md:grid-cols-4 md:gap-4 pb-2">
                  {SUGGESTIONS.map(({ text, note }) => (
                    <Card
                      key={text}
                      text={text}
                      note={note}
                      icon={icon4}
                      onClick={() => send({ text })}
                    />
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="result flex-grow w-full flex flex-col items-center">
              {responses.map((turn) => (
                <div key={turn.id} className="response-item mb-6 w-full max-w-[800px]">
                  <div className="flex items-start gap-2 mb-2">
                    <img src={assets.user_icon} alt="User" className="w-10 h-10 rounded-full" />
                    <div className="flex flex-col gap-2">
                      {turn.mediaFile && (
                        <SentMedia file={turn.mediaFile} kind={turn.mediaKind} />
                      )}
                      {turn.prompt && (
                        <p className="text-xl font-semibold">{turn.prompt}</p>
                      )}
                      {/* What the microphone actually heard, in the farmer's own
                          script - so a misheard word is visible rather than
                          buried in an answer that reads as slightly wrong. */}
                      {turn.transcript && (
                        <p className="text-lg text-gray-700">
                          <span className="text-xs uppercase tracking-wide text-gray-400 mr-2">
                            heard
                          </span>
                          {turn.transcript}
                        </p>
                      )}
                    </div>
                  </div>

                  {turn.vision && (
                    <div className="ml-12 mb-2 text-sm text-gray-600 bg-green-50 border border-green-100 rounded-lg px-3 py-2">
                      <span className="font-semibold">From the photo: </span>
                      {[
                        turn.vision.crop !== "unknown" && turn.vision.crop,
                        turn.vision.stage !== "unknown" && turn.vision.stage,
                        turn.vision.pest !== "unknown" &&
                          `${turn.vision.pest} (${turn.vision.confidence} confidence)`,
                        turn.vision.severity !== "unknown" && turn.vision.severity,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "nothing identifiable"}
                    </div>
                  )}

                  <div className="result-data flex items-start gap-2">
                    <div
                      className="w-9 h-9 shrink-0 rounded-full bg-gradient-to-br from-green-500 to-lime-500 text-white grid place-items-center text-sm font-bold select-none"
                      aria-hidden="true"
                    >
                      अ
                    </div>
                    <div
                      className={`p-4 rounded-lg bg-gray-50 border border-gray-100 flex-grow min-w-0 text-[15px] leading-8 ${
                        turn.failed ? "text-red-600" : ""
                      }`}
                    >
                      {turn.pending ? (
                        <div className="flex flex-col gap-[10px] w-full">
                          <hr className="border-none w-full h-[20px] bg-gradient-to-r from-[#9ed7ff] via-[#ffffff] to-[#9ed7ff] hr-animated" />
                          <hr className="border-none w-full h-[20px] bg-gradient-to-r from-[#9ed7ff] via-[#ffffff] to-[#9ed7ff] hr-animated" />
                          <hr className="border-none w-full h-[20px] bg-gradient-to-r from-[#9ed7ff] via-[#ffffff] to-[#9ed7ff] hr-animated" />
                        </div>
                      ) : (
                        <>
                          <div className="prose-answer">
                            <Markdown>{turn.response}</Markdown>
                          </div>
                          {!turn.failed && <Sources tools={turn.toolsUsed} />}
                          {isSpeechSupported() && !turn.failed && (
                            <button
                              type="button"
                              onClick={() =>
                                speakingId === turn.id ? hush() : readAloud(turn)
                              }
                              className="mt-2 inline-flex items-center gap-2 text-sm text-green-700 hover:text-green-900"
                              aria-label={
                                speakingId === turn.id
                                  ? "Stop reading the answer"
                                  : "Read the answer aloud"
                              }
                            >
                              {speakingId === turn.id ? (
                                <>
                                  <FaRegStopCircle /> Stop
                                </>
                              ) : (
                                <>
                                  <FaVolumeUp /> Listen
                                </>
                              )}
                            </button>
                          )}
                        </>
                      )}
                      </div>
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="px-4 bg-white sticky bottom-0">
        <MediaPreview
          selectedImage={selectedImage}
          selectedAudio={selectedAudio}
          clearSelectedImage={clearSelectedImage}
          clearSelectedAudio={clearSelectedAudio}
        />
        {isRecording && (
          <p className="text-center text-sm text-red-500 mt-2">
            Recording… press the microphone again to stop.
          </p>
        )}
        {micError && <p className="text-center text-sm text-red-500 mt-2">{micError}</p>}
        {speechError && (
          <p className="text-center text-sm text-amber-600 mt-2">{speechError}</p>
        )}
        <form
          onSubmit={handleSend}
          className="flex items-center border rounded-full shadow-sm p-3 mx-auto bg-gray-100 w-full max-w-[750px] mt-2"
        >
          <input
            onChange={(e) => setInput(e.target.value)}
            value={input}
            type="text"
            placeholder="Ask about your crop, in any language"
            className="flex-grow bg-gray-100 outline-none text-gray-700 placeholder-gray-500"
          />
          <div className="flex items-center space-x-3">
            <label htmlFor="image-upload" className="cursor-pointer opacity-65 hover:opacity-100">
              <FaImage />
              <input
                id="image-upload"
                type="file"
                accept="image/*"
                onChange={handleImageChange}
                style={{ display: "none" }}
              />
            </label>
            <button
              type="button"
              onClick={handleAudioRecord}
              aria-label={isRecording ? "Stop recording" : "Record a voice message"}
              className={isRecording ? "text-red-500 animate-pulse" : "opacity-65 hover:opacity-100"}
            >
              {isRecording ? <FaStop /> : <FaMicrophone />}
            </button>
            <button
              type="submit"
              disabled={loading || !canSend}
              aria-label="Send"
              className={loading || !canSend ? "opacity-30" : "opacity-65 hover:opacity-100"}
            >
              <IoMdSend />
            </button>
          </div>
        </form>
        <br />
      </div>
    </div>
  );
}

export default Main;
