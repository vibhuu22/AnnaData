import React from "react";

/**
 * The pieces every full-screen step shares, from the wireframes: a way back at
 * the top, the content, and one primary action pinned to the bottom where a
 * thumb already is.
 *
 * Full screen rather than a card inside the conversation because each of
 * these steps asks for one thing, and a farmer on a 360px phone should see
 * that thing and its button without scrolling past an answer to find it. The
 * conversation stays mounted underneath and is exactly where they left it
 * when they come back.
 */

export const primaryButton =
  "flex min-h-touch-lg w-full items-center justify-center rounded-card bg-leaf-600 px-4 text-lg font-semibold text-white transition-colors hover:bg-leaf-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 focus-visible:ring-offset-2 disabled:bg-soil-300";

export const secondaryButton =
  "flex min-h-touch-lg w-full items-center justify-center rounded-card border-2 border-soil-800 bg-white px-4 text-lg font-semibold text-soil-900 transition-colors hover:bg-soil-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600";

export const textButton =
  "inline-flex min-h-touch items-center text-base font-semibold text-soil-900 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 rounded disabled:text-soil-500 disabled:no-underline";

export const fieldClass =
  "w-full min-w-0 rounded-[10px] border-[1.5px] border-soil-400 bg-white px-3.5 text-base text-soil-900 outline-none placeholder:text-soil-500 focus:border-leaf-600 focus:ring-2 focus:ring-leaf-100";

export function BackIcon() {
  return (
    <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}

export function BackLink({ onClick, children }) {
  return (
    <button type="button" onClick={onClick} className={`${textButton} gap-1.5 no-underline`}>
      <BackIcon />
      {children}
    </button>
  );
}

/** The whole-screen frame. `actions` is pinned to the bottom. */
export function FlowScreen({ label, top, children, actions }) {
  return (
    <section
      aria-label={label}
      className="body relative flex min-h-screen w-full flex-col text-soil-900"
    >
      <div className="glass-soft mx-auto my-0 flex w-full max-w-[30rem] flex-grow flex-col gap-5 px-5 pb-6 pt-4 sm:my-6 sm:rounded-[28px] sm:px-6">
        {top && <div className="flex items-center justify-between gap-3">{top}</div>}
        {children}
        <div className="flex-grow" />
        {actions && <div className="sticky bottom-0 -mx-1 flex flex-col gap-2 px-1 pb-[env(safe-area-inset-bottom,0px)] pt-2">{actions}</div>}
      </div>
    </section>
  );
}

const STEPS = ["Confirm number", "About you", "Your farm"];

/** "Confirm number · About you · Your farm", on the number screens. */
export function StepLabels({ at }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-1.5 text-xs text-soil-600" aria-label="Steps">
      {STEPS.map((label, index) => (
        <li key={label} className="flex items-center gap-1.5">
          {index > 0 && <span aria-hidden="true">·</span>}
          <span
            aria-current={index === at ? "step" : undefined}
            className={index === at ? "font-bold text-soil-900" : undefined}
          >
            {label}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** "Step 1 of 2" and its bar, on the profile screens. */
export function StepBar({ step, of = 2 }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-xs font-bold text-soil-700">
        Step {step} of {of}
      </div>
      <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${of}, minmax(0, 1fr))` }} aria-hidden="true">
        {Array.from({ length: of }, (_, i) => (
          <div key={i} className={`h-1.5 rounded-full ${i < step ? "bg-leaf-600" : "bg-soil-200"}`} />
        ))}
      </div>
    </div>
  );
}

/** A tappable choice: languages, groups, crops. */
export function Chip({ active, children, className = "", ...rest }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      {...rest}
      className={`min-h-touch rounded-pill px-3.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 focus-visible:ring-offset-1 ${
        active
          ? "border-2 border-leaf-600 bg-leaf-600 font-semibold text-white"
          : "border-[1.5px] border-soil-400 bg-white text-soil-900 hover:border-leaf-500"
      } ${className}`}
    >
      {children}
    </button>
  );
}

/** "+91 ••••• 43210" - enough to recognise your own number, no more. */
export function maskPhone(phone) {
  const digits = String(phone || "").replace(/\D/g, "").slice(-10);
  if (digits.length < 5) return "";
  return `+91 ••••• ${digits.slice(-5)}`;
}

/**
 * The SMS number, when the deployment has told us it. Set
 * REACT_APP_SMS_NUMBER at build time; without it, the copy says SMS works
 * without inventing a number to send it to.
 */
export const SMS_NUMBER = (process.env.REACT_APP_SMS_NUMBER || "").trim();
