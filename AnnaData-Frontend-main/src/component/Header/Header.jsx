import React, { useContext, useEffect, useRef, useState } from "react";
import { Auth } from "../../Context/AuthProvider";
import { Context } from "../../Context/ContextProvider";
import { Flow } from "../../Context/Flow";
import { maskPhone } from "../Flow/ui";
import AnkurMark from "../Brand/AnkurMark";

/** The letter on a farmer's avatar: their name's first, else a person icon. */
function initial(user) {
  const name = (user?.name || "").trim();
  return name ? name[0].toUpperCase() : "";
}

const PersonIcon = ({ size = 20 }) => (
  <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
  </svg>
);

/**
 * The top-right corner: an avatar, not words. A guest sees an outline person
 * that opens sign-in; a signed-in farmer sees their initial, which opens a
 * small menu - who is signed in (a shared phone shows whose account is open),
 * their farm, home, and sign out. Closes on a tap outside, Escape, or a choice.
 */
function Profile({ onSignIn }) {
  const { user, signOut } = useContext(Auth) || {};
  const { goHome } = useContext(Context) || {};
  const openFlow = useContext(Flow);
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false);
    const escape = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  if (!user) {
    if (!onSignIn) return null;
    return (
      <button
        type="button"
        onClick={onSignIn}
        aria-label="Sign in"
        title="Sign in"
        className="grid h-10 w-10 place-items-center rounded-full border-[1.5px] border-soil-400 bg-white/60 text-soil-700 transition-colors hover:border-leaf-600 hover:text-leaf-700"
      >
        <PersonIcon />
      </button>
    );
  }

  const letter = initial(user);
  const choose = (action) => () => {
    setOpen(false);
    action?.();
  };
  const item = "flex min-h-touch w-full items-center rounded-xl px-3 text-left text-sm font-medium text-soil-900 hover:bg-leaf-50";
  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Your account"
        aria-haspopup="menu"
        aria-expanded={open}
        className="grid h-10 w-10 place-items-center rounded-full bg-leaf-600 text-base font-bold text-white shadow-sm ring-2 ring-white/70 transition-transform hover:scale-105"
      >
        {letter || <PersonIcon size={18} />}
      </button>
      {open && (
        <div role="menu" aria-label="Your account" className="glass absolute right-0 top-12 z-30 w-64 rounded-2xl p-2 shadow-lift">
          <div className="flex items-center gap-3 px-3 pb-2 pt-1.5">
            <span aria-hidden="true" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-leaf-600 font-bold text-white">
              {letter || <PersonIcon size={18} />}
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-semibold text-soil-900">{user.name || "Your account"}</span>
              <span className="text-xs text-soil-600">{maskPhone(user.phone || user.user_id)}</span>
              {user.district && <span className="truncate text-xs text-soil-600">{user.district}</span>}
            </span>
          </div>
          <div className="my-1 border-t border-soil-200" />
          {openFlow && (
            <button type="button" role="menuitem" onClick={choose(() => openFlow("profile"))} className={item}>
              Your farm
            </button>
          )}
          {goHome && (
            <button type="button" role="menuitem" onClick={choose(goHome)} className={item}>
              Home
            </button>
          )}
          {signOut && (
            <button type="button" role="menuitem" onClick={choose(signOut)} className={`${item} text-red-700 hover:bg-red-50`}>
              Sign out
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The title bar: the name on the left and the farmer's profile on the right.
 *
 * The name takes a signed-in farmer back to their home screen.
 */
function Header({ onSignIn }) {
  const { user } = useContext(Auth) || {};
  const { screen, goHome, responses } = useContext(Context) || {};
  const canGoHome = Boolean(user && responses?.length && screen !== "home" && goHome);

  return (
    <header className="glass sticky top-0 z-20 w-full !border-x-0 !border-t-0">
      {/* On a phone the menu opens from the bottom bar's "More", so nothing
          floats over this bar's left edge any more. */}
      <div className="mx-auto flex max-w-[900px] items-center justify-between gap-3 py-2 pl-4 pr-4 lg:pl-5">
        {canGoHome ? (
          <button type="button" onClick={goHome} className="flex min-h-touch items-center gap-2.5 text-lg font-bold tracking-tight text-soil-900" aria-label="AnnaData — home">
            <AnkurMark />
            AnnaData
          </button>
        ) : (
          <span className="flex min-h-touch items-center gap-2.5 text-lg font-bold tracking-tight text-soil-900">
            <AnkurMark />
            AnnaData
          </span>
        )}
        <Profile onSignIn={onSignIn} />
      </div>
    </header>
  );
}

export default Header;
