import React from "react";
import { FaCommentSms } from "react-icons/fa6";

/**
 * The persistent title bar.
 *
 * Two things earn their place here. The name, which previously vanished the
 * moment the first message was sent, leaving an unbranded chat window. And the
 * SMS badge: reaching a farmer with no smartphone is the whole point of this
 * system and the one thing a browser demo cannot show, so it is stated.
 */
function Header() {
  return (
    <header className="w-full border-b border-gray-200 bg-white/90 backdrop-blur sticky top-0 z-30">
      <div className="mx-auto max-w-[900px] flex items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-green-600 via-lime-500 to-yellow-500">
            Annadata
          </h1>
          <p className="hidden sm:block text-sm text-gray-500">
            Agricultural advice, in the farmer's own language
          </p>
        </div>
        <div
          className="flex items-center gap-2 text-xs sm:text-sm text-green-800 bg-green-50 border border-green-200 rounded-full px-3 py-1.5"
          title="The same agent answers over SMS through an Android handset acting as a gateway"
        >
          <FaCommentSms className="shrink-0" />
          <span className="whitespace-nowrap">
            Also works over <strong>SMS</strong>
            <span className="hidden md:inline"> — no smartphone needed</span>
          </span>
        </div>
      </div>
    </header>
  );
}

export default Header;
