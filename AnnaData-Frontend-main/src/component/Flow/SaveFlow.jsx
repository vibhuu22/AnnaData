import React, { useContext, useState } from "react";
import { Auth } from "../../Context/AuthProvider";
import SignIn from "../SignIn/SignIn";
import Onboarding from "../Onboarding/Onboarding";

/**
 * The full-screen steps, in order, from wherever the farmer started:
 *
 *   save     "Add farm details" under an answer: number, About you, Your farm
 *   signin   "Sign in" in the header: number, then the profile only if there
 *            is none yet
 *   profile  already signed in: "Edit" on the home screen, or finishing a
 *            profile that was left halfway
 *
 * `onClose` returns to the conversation, which stayed mounted underneath.
 */
function SaveFlow({ start = "save", onClose }) {
  const { needsOnboarding } = useContext(Auth);
  const [stage, setStage] = useState(start === "profile" ? "profile" : "number");
  const [editing] = useState(start === "profile" && !needsOnboarding);

  if (stage === "number") {
    return (
      <SignIn
        purpose={start === "save" ? "save" : "signin"}
        onBack={onClose}
        onVerified={(data) => {
          if (start === "save" || data?.needs_onboarding) setStage("profile");
          else onClose();
        }}
      />
    );
  }
  return <Onboarding onDone={onClose} editing={editing} />;
}

export default SaveFlow;
