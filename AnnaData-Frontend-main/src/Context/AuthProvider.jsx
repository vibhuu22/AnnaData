import React, {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  clearToken,
  fetchMe,
  getToken,
  onSessionExpired,
  signOut as endSession,
} from "../Config/session";

export const Auth = createContext();

/**
 * Who is signed in, and whether they have finished signing up.
 *
 * Deliberately separate from ContextProvider. That one owns a conversation;
 * this owns an identity, and the conversation is thrown away and rebuilt when
 * the identity changes. Keeping them in one provider made signing out a matter
 * of remembering to reset nine pieces of state.
 *
 * Three states the app routes on:
 *   checking          - a token exists and is being verified. Show nothing.
 *   no user           - the sign-in screen.
 *   user, not onboarded - the sign-up questions, which are skippable.
 */
const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [checking, setChecking] = useState(Boolean(getToken()));

  // A token in storage is not proof of anything - it may be expired, or signed
  // out from another device. It is checked once against the server on load.
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setChecking(false);
      return undefined;
    }
    (async () => {
      try {
        const data = await fetchMe();
        if (cancelled) return;
        setUser(data.user);
        setNeedsOnboarding(Boolean(data.needs_onboarding));
      } catch (e) {
        if (!cancelled) clearToken();
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // A 401 from any request anywhere, including mid-conversation.
  useEffect(
    () =>
      onSessionExpired(() => {
        setUser(null);
        setNeedsOnboarding(false);
      }),
    []
  );

  const signedIn = useCallback((data) => {
    setUser(data.user);
    setNeedsOnboarding(Boolean(data.needs_onboarding));
  }, []);

  const onboarded = useCallback((updated) => {
    if (updated) setUser(updated);
    setNeedsOnboarding(false);
  }, []);

  const signOut = useCallback(async () => {
    await endSession();
    setUser(null);
    setNeedsOnboarding(false);
  }, []);

  const value = useMemo(
    () => ({ user, setUser, needsOnboarding, checking, signedIn, onboarded, signOut }),
    [user, needsOnboarding, checking, signedIn, onboarded, signOut]
  );

  return <Auth.Provider value={value}>{children}</Auth.Provider>;
};

export default AuthProvider;
