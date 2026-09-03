import React, { useContext } from "react";
import Main from "./component/Main/Main";
import Sidebar from "./component/Sidebar/Sidebar";
import Header from "./component/Header/Header";
import SignIn from "./component/SignIn/SignIn";
import Onboarding from "./component/Onboarding/Onboarding";
import { Auth } from "./Context/AuthProvider";

/**
 * Which of the three screens the farmer is on.
 *
 * The gate is here rather than inside Main so that no part of the conversation
 * mounts before there is somebody to have it with - the history request would
 * otherwise fire without a token and come back 401 on every load.
 */
function App() {
  const { user, needsOnboarding, checking } = useContext(Auth);

  // A stored token is being checked against the server. Deliberately blank
  // rather than a spinner: it is one request, and a spinner that flashes for
  // 200ms reads as breakage rather than as progress.
  if (checking) {
    return <div className="body min-h-screen bg-soil-50" />;
  }

  if (!user) {
    return (
      <div className="body">
        <SignIn />
      </div>
    );
  }

  if (needsOnboarding) {
    return (
      <div className="body">
        <Onboarding />
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
        <div className="flex flex-col flex-grow min-w-0 h-screen">
          <Header />
          <Main />
        </div>
      </div>
    </div>
  );
}

export default App;
