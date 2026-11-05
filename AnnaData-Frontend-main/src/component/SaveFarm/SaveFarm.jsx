import React, { useState } from "react";
import SignIn from "../SignIn/SignIn";

/**
 * The offer to save, under an answer a guest has just read.
 *
 * This is where the phone number is asked for now: after the farmer has seen
 * the service work, and only if they choose to. "Not now" is a real answer and
 * the card goes away; the farmer keeps asking as a guest until they reach the
 * guest limit, when `limited` turns the same card into the way to continue.
 */
function SaveFarm({ limited = false, onDismiss }) {
  const [open, setOpen] = useState(false);

  if (open) {
    return <SignIn embedded onCancel={() => setOpen(false)} />;
  }

  return (
    <section
      aria-label="Save your farm"
      className="mb-6 ml-11 rounded-card border border-leaf-200 bg-leaf-50 p-4"
    >
      <h2 className="text-base font-semibold text-soil-900">
        {limited ? "Confirm your number to keep asking" : "Get answers for your own farm"}
      </h2>
      <p className="mt-1 text-sm text-soil-700">
        Confirm your number once, then tell us your district and crops. Your
        questions stay saved too.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="min-h-touch rounded-pill bg-leaf-600 px-5 text-sm font-semibold text-white transition-colors hover:bg-leaf-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 focus-visible:ring-offset-2"
        >
          Add farm details
        </button>
        {!limited && onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="min-h-touch px-2 text-sm text-soil-600 underline underline-offset-2"
          >
            Not now
          </button>
        )}
      </div>
    </section>
  );
}

export default SaveFarm;
