import React from "react";
import Main from "./compnent/Main/Main";
import Sidebar from "./compnent/Sidebar/Sidebar";
import Header from "./compnent/Header/Header";

function App() {
  return (
    // "body" is not decorative: index.css hangs the Outfit font off it.
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
