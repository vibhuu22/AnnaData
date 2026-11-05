import React, { useContext, useEffect, useState } from "react";
import Main from "./component/Main/Main";
import Sidebar from "./component/Sidebar/Sidebar";
import Header from "./component/Header/Header";
import SignIn from "./component/SignIn/SignIn";
import AppStatus from "./component/AppStatus";
import { Auth } from "./Context/AuthProvider";

/**
 * The chat, for everybody.
 *
 * This used to put the sign-in screen in front of the chat, so a farmer had to
 * give a phone number and wait for an SMS before seeing a single answer. Now
 * they ask first. A phone number is asked for only when they choose to save
 * their farm (the card under an answer), or when a returning farmer taps
 * "Sign in" in the header - the one case that opens the full sign-in screen.
 */
function App() {
  const { user, checking } = useContext(Auth);
  const [signingIn, setSigningIn] = useState(false);

  // Once somebody is signed in there is nothing left to sign in to.
  useEffect(() => {
    if (user) setSigningIn(false);
  }, [user]);

  // A stored token is being checked against the server. Deliberately blank
  // rather than a spinner: it is one request, and a spinner that flashes for
  // 200ms reads as breakage rather than as progress.
  if (checking) {
    return <div className="body min-h-screen bg-soil-50" />;
  }

  if (signingIn && !user) {
    return (
      <div className="body">
        <AppStatus />
        <SignIn onCancel={() => setSigningIn(false)} />
      </div>
    );
  }

  return (
    // "body" is not decorative: index.css hangs the app font off it.
    <div className="body bg-white">
      <div className="flex">
        <Sidebar />
        {/* min-w-0 so the chat column may shrink; without it a long unbroken
            string in an answer widens the flex child and scrolls the page. */}
        <div className="app-viewport flex flex-col flex-grow min-w-0">
          <Header onSignIn={() => setSigningIn(true)} />
          <AppStatus />
          <Main />
        </div>
      </div>
    </div>
  );
}

export default App;
