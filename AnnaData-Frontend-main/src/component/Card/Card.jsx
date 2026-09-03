import React from "react";

/**
 * A suggested question.
 *
 * Rendered as a button because it is one: the cards were once plain divs, so
 * the four example questions looked clickable and did nothing at all.
 *
 * The question itself is set at the app's body size rather than smaller. These
 * four cards are the only place most visitors will ever see this system answer
 * in Devanagari or Gurmukhi, and shrinking the type to make a tidy grid is
 * exactly the wrong trade: the script IS the demonstration.
 *
 * The previous version fixed the height at 190px, which suited the English
 * example and clipped nothing only by luck - a Devanagari question sets one
 * line longer than its Latin translation about as often as not. It now sizes to
 * its content with a floor, so no script is the one that overflows.
 */
const Card = ({ text, note, onClick }) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex min-h-[9.5rem] w-56 flex-shrink-0 flex-col justify-between gap-3 rounded-card border border-soil-200 bg-white p-4 text-left shadow-card transition-[transform,box-shadow,border-color] duration-150 hover:-translate-y-0.5 hover:border-leaf-300 hover:shadow-lift focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-500 focus-visible:ring-offset-2 active:translate-y-0 active:shadow-card md:w-auto"
    >
      <p className="text-base text-soil-800">{text}</p>

      <div className="flex items-end justify-between gap-2">
        {/* The script a question is written in is the point of the example, and
            not every reader can place it. The note says which language it is. */}
        {note && <p className="text-xs text-soil-500">{note}</p>}

        {/* Decorative. It replaces a 432-byte PNG of a speech bubble with no
            request at all, and it takes the leaf colour on interaction so the
            card has some answer to a thumb landing on it. */}
        <svg
          viewBox="0 0 20 20"
          className="h-5 w-5 flex-shrink-0 text-soil-300 transition-colors group-hover:text-leaf-500 group-active:text-leaf-600"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4 10h11M11 5l5 5-5 5" />
        </svg>
      </div>
    </button>
  );
};

export default Card;
