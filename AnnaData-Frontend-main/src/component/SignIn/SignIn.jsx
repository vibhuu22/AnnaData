import React, { useContext, useEffect, useRef, useState } from "react";
import { Auth } from "../../Context/AuthProvider";
import { requestCode, verifyCode } from "../../Config/session";
import {
  BackLink,
  FlowScreen,
  StepLabels,
  fieldClass,
  primaryButton,
  secondaryButton,
  textButton,
  SMS_NUMBER,
} from "../Flow/ui";

/**
 * Confirming a phone number with a code: three screens from the wireframes.
 *
 *   phone    Mobile number, and why we want it
 *   code     The 6-digit code, with a resend countdown
 *   trouble  "Code not arriving?", naming the reason when we know it
 *
 * A phone number, not an email, because user_id on SMS has always been the
 * farmer's number: the same number is the same account, so a farmer who starts
 * here and later texts the gateway has one history.
 *
 * Two purposes, worded differently because the farmer's reason differs:
 *   save    from "Add farm details", the first of three steps
 *   signin  from the header, for a farmer who has been here before
 *
 * Two attributes carry most of the weight on a real phone:
 *   autoComplete="one-time-code"  Android offers the code from the SMS itself
 *   inputMode="numeric"           a number pad, not a keyboard
 */

const CODE_TTL_MINUTES = 10;

function clock(seconds) {
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function spaced(digits) {
  return digits.length === 10 ? `+91 ${digits.slice(0, 5)} ${digits.slice(5)}` : `+91 ${digits}`;
}

function SignIn({ purpose = "signin", onBack, onVerified }) {
  const { signedIn } = useContext(Auth);
  const saving = purpose === "save";

  const [step, setStep] = useState("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // What went wrong last, so the trouble screen can name the actual reason
  // rather than listing every possible one.
  const [problem, setProblem] = useState(null);
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
      setTransport(data.transport || "");
      setCooldown(60);
      setProblem(null);
      setStep("code");
    } catch (e) {
      setError(e.message || "Could not send the code.");
      if (e.status === 429) setProblem({ kind: "limit", detail: e.message, wait: e.retryAfter });
      if (e.retryAfter) setCooldown(e.retryAfter);
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (event) => {
    event?.preventDefault();
    if (code.length !== 6 || busy) return;
    setBusy(true);
    setError("");
    try {
      const data = await verifyCode(digits, code);
      signedIn(data);
      onVerified?.(data);
    } catch (e) {
      setError(e.message || "That code did not work.");
      setProblem({ kind: e.status === 429 ? "limit" : "wrong", detail: e.message, wait: e.retryAfter });
      setCode("");
      codeRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const errorLine = error && (
    <p role="alert" className="text-sm text-red-700">
      {error}
    </p>
  );

  if (step === "phone") {
    return (
      <FlowScreen
        label={saving ? "Save your farm" : "Sign in"}
        top={onBack && <BackLink onClick={onBack}>{saving ? "Back to answer" : "Back"}</BackLink>}
        actions={
          <>
            <button
              type="submit"
              form="phone-form"
              disabled={!phoneLooksRight || busy || cooldown > 0}
              className={primaryButton}
            >
              {busy ? "Sending…" : cooldown > 0 ? `Wait ${clock(cooldown)}` : "Send code"}
            </button>
            {saving && onBack && (
              <button type="button" onClick={onBack} className={`${textButton} self-center`}>
                Not now — keep asking without saving
              </button>
            )}
          </>
        }
      >
        {saving && <StepLabels at={0} />}
        <h1 className="text-2xl font-bold leading-tight">
          {saving ? "Save your farm and your questions" : "Sign in"}
        </h1>
        <p className="text-base text-soil-700">
          {saving
            ? "First, confirm your mobile number. We will send a 6-digit code by SMS. After that, answers come for your own district and crops, and your questions stay saved."
            : "We will send a 6-digit code by SMS to confirm it is you."}
        </p>
        <form id="phone-form" onSubmit={askForCode} className="flex flex-col gap-2">
          <label htmlFor="phone" className="text-sm font-semibold">
            Mobile number
          </label>
          <div className="flex gap-2">
            <span className="flex h-14 select-none items-center rounded-[10px] border-[1.5px] border-soil-400 bg-soil-50 px-3.5 text-lg">
              +91
            </span>
            <input
              id="phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              autoFocus
              maxLength={14}
              placeholder="98765 43210"
              className={`${fieldClass} h-14 flex-1 text-lg tracking-wide`}
            />
          </div>
          <p className="text-sm text-soil-600">
            Use the number you text us from — your SMS questions and this app share one history.
          </p>
          {errorLine}
        </form>
      </FlowScreen>
    );
  }

  if (step === "trouble") {
    const card = (title, body, strong = false) => (
      <div
        className={`flex flex-col gap-1.5 rounded-xl px-4 py-3.5 ${
          strong ? "border-2 border-soil-900" : "border-[1.5px] border-soil-400"
        }`}
      >
        <div className="text-base font-bold">{title}</div>
        <div className="text-sm text-soil-700">{body}</div>
      </div>
    );
    return (
      <FlowScreen
        label="Code not arriving"
        top={<BackLink onClick={() => setStep("code")}>Back to code</BackLink>}
        actions={
          <button
            type="button"
            onClick={() => {
              setStep("phone");
              setCode("");
              setError("");
            }}
            className={secondaryButton}
          >
            Use a different number
          </button>
        }
      >
        <h1 className="text-2xl font-bold leading-tight">Code not arriving?</h1>
        {problem?.kind === "wrong" &&
          card(
            "That code does not match",
            `${problem.detail ? `${problem.detail}. ` : ""}Check the latest SMS — an older code stops working when a new one is sent.`,
            true
          )}
        {problem?.kind === "limit" &&
          card(
            "Too many codes requested",
            `You can ask for 5 codes an hour.${problem.wait ? ` Try again in ${clock(problem.wait)}.` : ""}${
              SMS_NUMBER ? ` Meanwhile you can text your question to ${SMS_NUMBER} — that does not need a code.` : ""
            }`,
            true
          )}
        {card(
          "Our sending phone may be offline",
          "If no code arrives in 2 minutes, the problem is most likely on our side, not your number. SMS answers use the same phone, so please try again later.",
          !problem
        )}
        {card("Code expired", `Codes work for ${CODE_TTL_MINUTES} minutes. Ask for a new one.`)}
      </FlowScreen>
    );
  }

  return (
    <FlowScreen
      label="Enter the code"
      top={
        <BackLink
          onClick={() => {
            setStep("phone");
            setCode("");
            setError("");
          }}
        >
          Change number
        </BackLink>
      }
      actions={
        <button type="submit" form="code-form" disabled={code.length !== 6 || busy} className={primaryButton}>
          {busy ? "Checking…" : saving ? "Verify and continue" : "Sign in"}
        </button>
      }
    >
      <h1 className="text-3xl font-bold leading-tight">Enter the code</h1>
      <p className="text-lg text-soil-700">
        We sent a 6-digit code by SMS to <strong className="text-soil-900">{spaced(digits)}</strong>. It can
        take up to a minute to arrive.
      </p>
      <form id="code-form" onSubmit={submitCode} className="flex flex-col gap-2">
        <label htmlFor="code" className="text-sm font-semibold">
          6-digit code
        </label>
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
          placeholder="• • • • • •"
          className={`${fieldClass} h-16 text-center text-3xl tracking-[0.4em] placeholder:tracking-[0.2em]`}
        />
        <p className="text-sm text-soil-600">The code works for {CODE_TTL_MINUTES} minutes.</p>
        {errorLine}
        {transport === "console" && (
          // Development only. Without this the code is in a server log and
          // nobody testing locally can find it.
          <p className="rounded-lg bg-grain-50 px-3 py-2 text-xs text-grain-700">
            No SMS gateway is configured, so the code was printed to the backend log instead of being sent.
          </p>
        )}
      </form>
      <div className="flex flex-col items-start gap-1">
        <button type="button" onClick={askForCode} disabled={cooldown > 0 || busy} className={textButton}>
          {cooldown > 0 ? `Resend code in ${clock(cooldown)}` : "Resend code"}
        </button>
        <button type="button" onClick={() => setStep("trouble")} className={`${textButton} underline`}>
          Code not arriving?
        </button>
      </div>
    </FlowScreen>
  );
}

export default SignIn;
