/**
 * Ankur's head and sprout, for the header at 32 px - the place the plain "अ"
 * tile used to be. Drawn inline so it is crisp at any pixel density and costs
 * no request on a slow connection.
 *
 * At this size the master character is reduced, as the brand sheet asks: no
 * arms, legs or blush (they turn to mush below ~48 px), thicker eyes and smile,
 * and the two-leaf sprout kept distinct on top. Colours: leaf-600 tile, Ankur
 * tan body, light leaf sprout so it reads on the dark green.
 */
function AnkurMark({ className = "h-8 w-8" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="14" fill="#1F6B45" />
      <path d="M32 21 C44 21 50 31 50 42 C50 53 42 59 32 59 C22 59 14 53 14 42 C14 31 20 21 32 21 Z" fill="#C8935A" />
      <path d="M32 22 C32.5 19 32.5 16.5 31.5 14" fill="none" stroke="#A8DDB4" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M31.5 14.5 C27.5 8.5 20 7.5 15.5 11 C19 16.5 26.5 17 31.5 14.5 Z" fill="#7CC08F" />
      <path d="M32.5 14.5 C37 6.5 45.5 4.5 50 8.5 C46.5 15.5 38 17 32.5 14.5 Z" fill="#A8DDB4" />
      <circle cx="25.5" cy="38" r="2.9" fill="#2A2721" />
      <circle cx="38.5" cy="38" r="2.9" fill="#2A2721" />
      <path d="M28 45 Q32 48.5 36 45" fill="none" stroke="#2A2721" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export default AnkurMark;
