import { createContext } from "react";

/**
 * Opens one of the full-screen step sequences ("save", "signin", "profile").
 * A function rather than state, so the components that open a flow - the save
 * card, the home screen's Edit - need nothing else from App.
 */
export const Flow = createContext(() => {});
