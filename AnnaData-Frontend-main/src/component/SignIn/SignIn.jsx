import React, { useContext, useEffect, useRef, useState } from "react";
import { FaCommentSms } from "react-icons/fa6";
import { Auth } from "../../Context/AuthProvider";
import { requestCode, verifyCode } from "../../Config/session";

/**
 * Signing in with a phone number and a code.
 *
 * A phone number, not an email, because user_id on SMS has always been the
 * farmer's number: signing in with the same number produces the same account, so
 * a farmer who starts in the browser and later texts the gateway is one farmer
 * with one history.
 *
 * Two things here carry most of the weight on a real phone, and both are one
 * attribute each:
 *
 *   autoComplete="one-time-code"  Android offers the code straight from the SMS
 *                                 notification, so the farmer never leaves the
 *                                 page to go and read it. This is the single
 *                                 biggest reduction in friction on this screen.
 *   inputMode="numeric"           a number pad, not a QWERTY keyboard.
 *
 * Two ways in. Full screen, from the header's "Sign in", for a farmer who has
 * been here before. And `embedded`, under an answer, when a farmer who has just
 * seen it work taps "Add farm details" - the first of three steps (confirm
 * number, about you, your farm), worded as saving rather than as signing in,
 * because that is the reason they are giving a number at all.
 */
const STEPS = ["Confirm number", "About you", "Your farm"];

export function Progress({ at }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs" aria-label="Steps">
      {STEPS.map((label, index) => (
        <li key={label} className="flex items-center gap-2">
          {index > 0 && <span aria-hidden="true" className="text-soil-300">·</span>}
          <span
            aria-current={index === at ? "step" : undefined}
            className={
              index === at
                ? "font-semibold text-leaf-700"
                : index < at
                  ? "text-soil-600"
                  : "text-soil-400"
            }
          >
            {label}
          </span>
        </li>
      ))}
    </ol>
  );
}

function SignIn({ embedded = false, onCancel }) {
  const { signedIn } = useContext(Auth);

  const [step, setStep] = useState("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [masked, setMasked] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [transport, setTransport] = useState("");

  const codeRef = useRef(null);

  // Countdown to the next allowed resend. The backend enforces this; the screen
  // only shows it, so a farmer is not left pressing a button that will refuse.
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  useEffect(() => {
    if (step === "code") codeRef.current?.focus();
  }, [step]);

  const digits = phone.replace(/\D/g, "").slice(-10);
  const phoneLooksRight = digits.length === 10 && "6789".includes(digits[0]);

  const askForCode = async (event) => {
    event?.preventDefault();
    if (!phoneLooksRight || busy) return;
    setBusy(true);
    setError("");
    try {
      const data = await requestCode(digits);
      setMasked(data.phone || "");
      setTransport(data.transport || "");
      setCooldown(60);
      setStep("code");
    } catch (e) {
      setError(e.message || "Could not send the code.");
      if (e.retryAfter) setCooldown(e.retryAfter);
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (event) => {
    event?.preventDefault();
    if (code.replace(/\D/g, "").length !== 6 || busy) return;
    setBusy(true);
    setError("");
    try {
      signedIn(await verifyCode(digits, code.replace(/\D/g, "")));
    } catch (e) {
      setError(e.message || "That code did not work.");
      setCode("");
      codeRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const form = (
        <div className={`${embedded ? "mt-4" : "mt-8"} rounded-card border border-soil-200 bg-white p-5 shadow-card`}>
          {step === "phone" ? (
            <form onSubmit={askForCode}>
              <label htmlFor="phone" className="block text-base font-semibold text-soil-900">
                Your mobile number
              </label>
              <p className="mt-1 text-sm text-soil-600">
                {embedded
                  ? "We will text you a 6-digit code. Your farm and your questions are saved to this number."
                  : "We will text you a 6-digit code to sign in."}
              </p>

              <div className="mt-4 flex items-center rounded-pill border border-soil-300 bg-white focus-within:border-leaf-500 focus-within:ring-2 focus-within:ring-leaf-100">
                <span className="select-none border-r border-soil-200 px-3 py-3 text-base text-soil-600">
                  +91
                </span>
                <input
                  id="phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  type="tel"
                  inputMode="numeric"
                  autoComplete="tel"
                  autoFocus
                  maxLength={14}
                  placeholder="98765 43210"
                  className="min-h-touch w-full min-w-0 flex-grow rounded-r-pill bg-transparent px-3 text-lg tracking-wide text-soil-900 outline-none placeholder:text-soil-400"
                />
              </div>

              {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

              <button
                type="submit"
                disabled={!phoneLooksRight || busy || cooldown > 0}
                className="mt-5 min-h-touch-lg w-full rounded-pill bg-leaf-600 text-base font-semibold text-white transition-colors hover:bg-leaf-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 focus-visible:ring-offset-2 disabled:bg-soil-300"
              >
                {busy
                  ? "Sending…"
                  : cooldown > 0
                    ? `Wait ${cooldown}s`
                    : "Send me a code"}
              </button>
            </form>
          ) : (
            <form onSubmit={submitCode}>
              <label htmlFor="code" className="block text-base font-semibold text-soil-900">
                Enter the code
              </label>
              <p className="mt-1 text-sm text-soil-600">
                Sent to {masked || `+91 ${digits}`}.
              </p>

              <input
                id="code"
                ref={codeRef}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                type="text"
                inputMode="numeric"
                // The attribute that lets Android fill this from the SMS itself.
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="123456"
                className="mt-4 min-h-touch-lg w-full rounded-card border border-soil-300 bg-white text-center text-3xl tracking-[0.4em] text-soil-900 outline-none focus:border-leaf-500 focus:ring-2 focus:ring-leaf-100 placeholder:tracking-[0.4em] placeholder:text-soil-300"
              />

              {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

              {transport === "console" && (
                // Development only. Without this the code is in a server log and
                // nobody testing locally can find it.
                <p className="mt-3 rounded-lg bg-grain-50 px-3 py-2 text-xs text-grain-700">
                  No SMS gateway is configured, so the code was printed to the
                  backend log instead of being sent.
                </p>
              )}

              <button
                type="submit"
                disabled={code.length !== 6 || busy}
                className="mt-5 min-h-touch-lg w-full rounded-pill bg-leaf-600 text-base font-semibold text-white transition-colors hover:bg-leaf-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 focus-visible:ring-offset-2 disabled:bg-soil-300"
              >
                {busy ? "Checking…" : embedded ? "Confirm" : "Sign in"}
              </button>

              <div className="mt-4 flex items-center justify-between text-sm">
                <button
                  type="button"
                  onClick={() => {
                    setStep("phone");
                    setCode("");
                    setError("");
                  }}
                  className="min-h-touch text-soil-600 underline underline-offset-2"
                >
                  Change number
                </button>
                <button
                  type="button"
                  onClick={askForCode}
                  disabled={cooldown > 0 || busy}
                  className="min-h-touch text-leaf-700 underline underline-offset-2 disabled:text-soil-400 disabled:no-underline"
                >
                  {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                </button>
              </div>

              {/* Said plainly, because the honest reasons are ours, not the
                  farmer's: codes go out from one Android phone, which may be
                  offline. Better a farmer knows to wait than re-enter a number
                  that was right all along. */}
              <details className="mt-3 text-sm text-soil-600">
                <summary className="min-h-touch cursor-pointer py-2 text-soil-700">
                  Code not arriving?
                </summary>
                <p className="pb-1 text-xs leading-relaxed text-soil-600">
                  Codes are sent from a single phone and can take a minute or two.
                  Each code works for 10 minutes, and up to 5 codes can be sent in
                  an hour. Check the number above is yours, then wait before
                  asking for another.
                </p>
              </details>
            </form>
          )}
        </div>
  );

  const cancel = onCancel && (
    <button
      type="button"
      onClick={onCancel}
      className="mx-auto mt-4 block min-h-touch text-sm text-soil-600 underline underline-offset-2"
    >
      {embedded ? "Not now — keep asking without saving" : "Back to asking"}
    </button>
  );

  if (embedded) {
    return (
      <section aria-label="Save your farm" className="mt-6 rounded-card bg-soil-50 px-4 py-6">
        <div className="mx-auto w-full max-w-[30rem]">
          <Progress at={0} />
          <h2 className="mt-3 text-2xl font-bold text-soil-900">
            Save your farm and your questions
          </h2>
          {form}
          {cancel}
        </div>
      </section>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-soil-50 px-4 py-10">
      <div className="w-full max-w-[24rem]">
        <h1 className="bg-gradient-to-r from-leaf-700 via-leaf-500 to-grain-500 bg-clip-text text-center text-3xl font-bold text-transparent">
          Annadata
        </h1>
        <p className="mt-2 text-center text-sm text-soil-600">
          Agricultural advice, in your own language
        </p>

        {form}
        {cancel}

        <p className="mt-6 flex items-center justify-center gap-2 text-center text-xs text-soil-500">
          <FaCommentSms className="shrink-0" />
          No smartphone? The same advice works over plain SMS.
        </p>
      </div>
    </div>
  );
}

export default SignIn;
