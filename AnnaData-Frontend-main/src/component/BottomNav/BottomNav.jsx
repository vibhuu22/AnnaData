import { t } from '../../Config/uiLanguage';
import React, { useContext } from "react";
import { FaHouse, FaCompass, FaNewspaper, FaBars, FaMicrophone } from "react-icons/fa6";
import { Context } from "../../Context/ContextProvider";

/**
 * The phone's main navigation, at the bottom where a thumb reaches it.
 *
 * A menu behind a corner button hides the app's main actions from exactly
 * the farmers least used to apps; on a phone these four places and the
 * microphone are now always in view. Talking is the centre and the biggest
 * target, because for many farmers it is the way in. "More" opens the
 * drawer, which keeps what is used less: recent chats, the area card,
 * the account.
 *
 * Phones only (below lg): on a wide screen the sidebar is a panel and already
 * shows all of this. Not on the chat screen, which has its own composer.
 */
function BottomNav({ onTalk }) {
  const { screen, setScreen, goHome, setMenuOpen } = useContext(Context);
  const atHome = screen === "ask" || screen === "home";

  const tab = (label, icon, active, onClick) => (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`flex min-h-touch w-16 flex-col items-center justify-center gap-1 rounded-2xl text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 ${
        active ? "font-semibold text-leaf-800" : "text-soil-700"
      }`}
    >
      <span aria-hidden="true" className="text-xl">{icon}</span>
      {label}
    </button>
  );

  return (
    <nav
      aria-label={t("Main")}
      className="glass fixed inset-x-0 bottom-0 z-20 !border-x-0 !border-b-0 pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      <div className="mx-auto flex h-16 max-w-[30rem] items-center justify-around px-2">
        {tab(t("Home"), <FaHouse />, atHome, () => goHome?.())}
        {tab(t("Explore"), <FaCompass />, screen === "explore", () => setScreen?.("explore"))}
        <button
          type="button"
          onClick={onTalk}
          aria-label={t("Talk")}
          className="-mt-8 grid h-[4.5rem] w-[4.5rem] shrink-0 place-items-center rounded-full bg-leaf-600 text-white shadow-lift transition-colors hover:bg-leaf-700 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-leaf-200 focus-visible:ring-offset-2"
        >
          <FaMicrophone aria-hidden="true" className="h-7 w-7" />
        </button>
        {tab(t("News"), <FaNewspaper />, screen === "news", () => setScreen?.("news"))}
        {tab(t("More"), <FaBars />, false, () => setMenuOpen?.(true))}
      </div>
    </nav>
  );
}

export default BottomNav;
