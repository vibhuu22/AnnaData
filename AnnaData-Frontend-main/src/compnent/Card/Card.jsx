import React from "react";

/**
 * A suggested question. Rendered as a button because it is one: the cards were
 * previously plain divs, so the four example questions on the landing screen
 * looked clickable and did nothing at all.
 */
const Card = ({ text, note, icon, onClick }) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className="relative p-4 flex flex-col justify-between bg-[#eef2f7] hover:bg-[#e0e7f0] hover:-translate-y-0.5 transition duration-150 rounded-2xl h-[190px] sm:h-[200px] w-52 md:w-auto flex-shrink-0 text-left border border-transparent hover:border-gray-300"
    >
      <p className="text-[15px] leading-snug text-black opacity-85">{text}</p>
      <div>
        {/* The script a question is written in is the point of the example, and
            not every reader can place it. The note says which language it is. */}
        {note && <p className="text-xs text-gray-500 pr-9">{note}</p>}
      </div>
      <div className="absolute bottom-3 right-3 bg-white rounded-full p-2">
        <img src={icon} alt="" className="w-5 h-5" />
      </div>
    </button>
  );
};

export default Card;
