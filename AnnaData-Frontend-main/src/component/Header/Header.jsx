import React, { useContext } from "react";
import { Auth } from "../../Context/AuthProvider";
import { Context } from "../../Context/ContextProvider";
import { maskPhone, textButton } from "../Flow/ui";

/**
 * The title bar, as in the wireframes: the name on the left and one thing on
 * the right - "Sign in" for someone who has not, and for a farmer who has,
 * their own number, masked, so a shared phone shows whose account is open.
 *
 * The name takes a signed-in farmer back to their home screen.
 */
function Header({ onSignIn }) {
  const { user, signOut } = useContext(Auth) || {};
  const { screen, goHome, responses } = useContext(Context) || {};
  const canGoHome = Boolean(user && responses?.length && screen !== "home" && goHome);

  return (
    <header className="sticky top-0 z-30 w-full border-b border-soil-200 bg-white/95 backdrop-blur">
      {/*
        pl-16 below the large breakpoint, because the sidebar's menu button is
        position:fixed at the top-left corner and floats above this bar.
      */}
      <div className="mx-auto flex max-w-[900px] items-center justify-between gap-3 py-2 pl-16 pr-4 lg:pl-5">
        {canGoHome ? (
          <button type="button" onClick={goHome} className="min-h-touch text-lg font-bold text-soil-900" aria-label="AnnaData — home">
            AnnaData
          </button>
        ) : (
          <span className="flex min-h-touch items-center text-lg font-bold text-soil-900">AnnaData</span>
        )}
        {!user && onSignIn && (
          <button type="button" onClick={onSignIn} className={textButton}>
            Sign in
          </button>
        )}
        {user && screen === "home" && signOut && (
          <button type="button" onClick={signOut} className={textButton}>
            Sign out
          </button>
        )}
        {user && screen !== "home" && (
          <span className="text-xs text-soil-600">{maskPhone(user.phone || user.user_id)}</span>
        )}
      </div>
    </header>
  );
}

export default Header;
