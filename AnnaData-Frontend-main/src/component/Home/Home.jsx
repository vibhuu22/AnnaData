import React, { useContext } from "react";
import { Auth } from "../../Context/AuthProvider";
import { Context } from "../../Context/ContextProvider";
import { Flow } from "../../Context/Flow";
import { primaryButton, textButton, SMS_NUMBER } from "../Flow/ui";

/**
 * A returning farmer's first screen (wireframe 8): who we think they are, the
 * farm we will answer for, a way to ask, and what they asked before.
 *
 * The farm summary is here so a wrong district is visible - and fixable with
 * one tap - before it quietly shapes every answer.
 */
const title = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function when(at) {
  if (!at) return "";
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

function Home() {
  const { user } = useContext(Auth);
  const { chats = [], newChat, openChat } = useContext(Context);
  const openFlow = useContext(Flow);

  const farm = [
    user?.district,
    (user?.crops || []).map(title).join(", "),
    user?.total_area_text,
  ].filter(Boolean);
  const recent = chats.slice(0, 6);
  const firstName = (user?.name || "").trim().split(/\s+/)[0];

  return (
    <div className="mx-auto flex w-full max-w-[30rem] flex-grow flex-col gap-4 px-5 py-5">
      <h1 className="text-2xl font-bold leading-tight text-soil-900">
        Welcome back{firstName ? `, ${firstName}` : ""}
      </h1>

      <div className="card-read flex items-center justify-between gap-3 rounded-[20px] p-4">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="text-xs font-bold text-soil-700">Your farm</div>
          <div className="text-base font-semibold text-soil-900">
            {farm.length ? farm.join(" · ") : "Not added yet"}
          </div>
        </div>
        <button type="button" onClick={() => openFlow("profile")} className={`${textButton} shrink-0`}>
          {farm.length ? "Edit" : "Add"}
        </button>
      </div>

      <button type="button" onClick={newChat} className={`${primaryButton} gap-2 !rounded-full shadow-lift`}>
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        </svg>
        New chat
      </button>

      {recent.length > 0 && (
        <section aria-label="Recent chats" className="flex flex-col gap-2">
          <h2 className="text-sm font-bold text-soil-900">Recent chats</h2>
          {recent.map((chat) => (
            <button
              key={chat.id}
              type="button"
              onClick={() => openChat(chat.id)}
              className="glass-soft flex min-h-touch-lg items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left transition-transform hover:-translate-y-0.5"
            >
              <span className="flex min-w-0 flex-col">
                <span className="line-clamp-2 text-sm font-medium text-soil-900">{chat.title}</span>
                <span className="text-xs text-soil-600">
                  {chat.count} {chat.count === 1 ? "question" : "questions"}
                </span>
              </span>
              <span className="shrink-0 text-xs text-soil-600">{when(chat.at)}</span>
            </button>
          ))}
        </section>
      )}

      <div className="flex-grow" />
      <p className="text-center text-sm text-soil-600">
        Questions you text to {SMS_NUMBER || "AnnaData by SMS"} appear here too — one history for both.
      </p>
    </div>
  );
}

export default Home;
