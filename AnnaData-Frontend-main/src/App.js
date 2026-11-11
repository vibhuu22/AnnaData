import React, { useContext, useState } from "react";
import Main from "./component/Main/Main";
import Sidebar from "./component/Sidebar/Sidebar";
import Header from "./component/Header/Header";
import SaveFlow from "./component/Flow/SaveFlow";
import AppStatus from "./component/AppStatus";
import { Auth } from "./Context/AuthProvider";
import { Flow } from "./Context/Flow";
import { useUiLanguage } from './Config/uiLanguage';

/**
 * The chat, for everybody, and the full-screen steps on top of it.
 *
 * A farmer asks first. A phone number is asked for only when they choose to
 * save their farm ("Add farm details" under an answer) or tap "Sign in" in the
 * header. Those steps take the whole screen, as in the wireframes, but the
 * conversation is only hidden behind them, never unmounted - so coming back
 * from "Not now" or from a finished profile lands exactly where they were.
 */
function App() {
  const language = useUiLanguage();
  React.useEffect(() => { document.documentElement.lang = language; }, [language]);
  const { checking } = useContext(Auth);
  const [flow, setFlow] = useState(null);

  // A stored token is being checked against the server. Deliberately blank
  // rather than a spinner: it is one request, and a spinner that flashes for
  // 200ms reads as breakage rather than as progress.
  if (checking) {
    return <div className="body min-h-screen bg-[#eaf2ec]" />;
  }

  return (
    <Flow.Provider value={setFlow}>
      {/* The soft field of colour every glass surface sits over. */}
      <div className="app-backdrop" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      {flow && (
        <div className="body relative z-10">
          <SaveFlow start={flow} onClose={() => setFlow(null)} />
        </div>
      )}
      {/* "body" is not decorative: index.css hangs the app font off it. */}
      <div className={`body relative z-10 ${flow ? "hidden" : ""}`} aria-hidden={flow ? true : undefined}>
        <div className="flex">
          <Sidebar />
          {/* min-w-0 so the chat column may shrink; without it a long unbroken
              string in an answer widens the flex child and scrolls the page. */}
          <div className="app-viewport flex min-w-0 flex-grow flex-col">
            <Header onSignIn={() => setFlow("signin")} />
            <AppStatus />
            <Main />
          </div>
        </div>
      </div>
    </Flow.Provider>
  );
}

export default App;
