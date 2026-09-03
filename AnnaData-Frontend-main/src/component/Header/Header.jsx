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
    <header className="sticky top-0 z-30 w-full border-b border-soil-200 bg-white/90 backdrop-blur">
      {/*
        pl-16 below the large breakpoint, because the sidebar's menu button is
        position:fixed at the top-left corner and floats above this bar. At
        360px it was landing squarely on the "A" of the wordmark.
      */}
      <div className="mx-auto flex max-w-[900px] items-center justify-between gap-4 py-3 pl-16 pr-4 lg:pl-4">
        <div className="flex items-baseline gap-3">
          <h1 className="bg-gradient-to-r from-leaf-700 via-leaf-500 to-grain-500 bg-clip-text text-2xl font-bold text-transparent">
            Annadata
          </h1>
          <p className="hidden text-sm text-soil-500 sm:block">
            Agricultural advice, in the farmer's own language
          </p>
        </div>
        <div
          className="flex shrink-0 items-center gap-2 rounded-pill border border-leaf-200 bg-leaf-50 px-3 py-1.5 text-xs text-leaf-800 sm:text-sm"
          title="The same agent answers over SMS through an Android handset acting as a gateway"
        >
          <FaCommentSms className="shrink-0" />
          {/*
            The badge sheds words rather than the page growing a horizontal
            scrollbar. At 360px, once the wordmark has been pushed clear of the
            menu button, there is only room for the icon and the word itself -
            and the icon plus "SMS" still says the thing that matters.
          */}
          <span className="whitespace-nowrap">
            <span className="hidden sm:inline">Also works over </span>
            <strong>SMS</strong>
            <span className="hidden md:inline"> — no smartphone needed</span>
          </span>
        </div>
      </div>
    </header>
  );
}

export default Header;
