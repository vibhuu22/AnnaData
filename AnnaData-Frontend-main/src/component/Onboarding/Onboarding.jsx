import React, { useContext, useEffect, useRef, useState } from "react";
import { FaLocationDot } from "react-icons/fa6";
import { Auth } from "../../Context/AuthProvider";
import { saveProfile } from "../../Config/session";
import { Progress } from "../SignIn/SignIn";

/**
 * The sign-up questions, after the number is confirmed.
 *
 * TWO SHORT STEPS, About you and Your farm. This was one screen, on the
 * argument that every Next button is a place to abandon. It became two when
 * the phone number moved behind "Add farm details": the farmer arrives here
 * having just chosen to save, so the cost of one more tap is low, and the
 * first step is the quick personal part that gets them moving before the
 * slower farm questions. Step one is saved on its own, so a farmer who leaves
 * halfway still keeps their name.
 *
 * EVERY FIELD IS OPTIONAL, including all of them at once. A farmer who gives a
 * district and nothing else is worth more than one who gave up on a required
 * field, and the agent already knows how to ask for a missing crop or district
 * mid-conversation - that is what `missing_slots` is for. "Skip" is a real
 * button, not a dark pattern.
 *
 * WHY THESE FOUR. District decides which mandi a price comes from. Land area
 * turns a dose from a rate per hectare into a quantity to buy, which is the
 * difference between advice and an instruction. Crop lets an answer skip asking
 * "which crop?" - and is filled in already when the question they asked named
 * one. Name is so the farmer is greeted rather than processed.
 *
 * LANGUAGE IS STORED, NOT YET USED TO ANSWER. Replies follow the script the
 * farmer writes in, whatever is chosen here, and the copy says so rather than
 * promising that choosing Hindi changes anything today.
 *
 * FARMER GROUP is asked because the service is sold to FPOs, cooperatives and
 * SHGs rather than to farmers, and this is how usage is tied to the
 * organisation paying for it.
 *
 * How long it takes is measured and sent, because "a one-minute onboarding"
 * should be a number somebody checked rather than a hope.
 */

const CROPS = [
  "rice", "wheat", "cotton", "sugarcane", "maize", "soybean",
  "mustard", "gram", "potato", "onion", "groundnut", "tomato",
];

const UNITS = ["acre", "bigha", "hectare", "guntha"];

// Profile `language` values, in each language's own script so a farmer can
// find theirs without reading English.
const LANGUAGES = [
  { code: "hi-IN", label: "हिंदी" },
  { code: "hi-Latn", label: "Hinglish" },
  { code: "bn-IN", label: "বাংলা" },
  { code: "pa-IN", label: "ਪੰਜਾਬੀ" },
  { code: "en-IN", label: "English" },
];

const GROUPS = [
  { code: "fpo", label: "FPO" },
  { code: "cooperative", label: "Cooperative" },
  { code: "shg", label: "Self-help group" },
  { code: "none", label: "No" },
];

const inputClass =
  "mt-2 min-h-touch w-full rounded-card border border-soil-300 bg-white px-3 text-base text-soil-900 outline-none focus:border-leaf-500 focus:ring-2 focus:ring-leaf-100 placeholder:text-soil-400";

function Chip({ active, children, ...rest }) {
  return (
    <button
      type="button"
      {...rest}
      className={`min-h-touch rounded-pill border px-4 text-sm transition-colors ${
        active
          ? "border-leaf-600 bg-leaf-600 text-white"
          : "border-soil-300 bg-white text-soil-700 hover:border-leaf-400"
      }`}
    >
      {children}
    </button>
  );
}

function Onboarding({ embedded = false }) {
  const { user, setUser, onboarded } = useContext(Auth);

  const [step, setStep] = useState("about");
  const [name, setName] = useState(user?.name || "");
  const [language, setLanguage] = useState(user?.language || "");
  const [group, setGroup] = useState(user?.farmer_group || "");
  const [groupName, setGroupName] = useState(user?.farmer_group_name || "");
  const [district, setDistrict] = useState(user?.district || "");
  const [state, setState] = useState(user?.state || "");
  const [coords, setCoords] = useState(null);
  const [crops, setCrops] = useState(user?.crops || []);
  const [area, setArea] = useState("");
  const [areaUnit, setAreaUnit] = useState("acre");
  const [locating, setLocating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Wall-clock from the moment the form is on screen to the moment it is sent.
  const startedAt = useRef(performance.now());
  const topRef = useRef(null);

  useEffect(() => {
    startedAt.current = performance.now();
  }, []);

  // The second step replaces the first in place; bring its heading into view
  // rather than leaving the farmer looking at the bottom of a shorter card.
  useEffect(() => {
    if (step === "farm") topRef.current?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  }, [step]);

  // A crop the question already named may not be one of the twelve chips.
  const cropChoices = [...CROPS, ...(user?.crops || []).filter((c) => !CROPS.includes(c))];

  const toggleCrop = (crop) =>
    setCrops((prev) =>
      prev.includes(crop) ? prev.filter((c) => c !== crop) : [...prev, crop]
    );

  /** One tap instead of typing a district name, which is the slowest field. */
  const useMyLocation = async () => {
    if (!("geolocation" in navigator)) {
      setError("This browser cannot find your location. Please type your district.");
      return;
    }
    setLocating(true);
    setError("");
    try {
      const position = await new Promise((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 300000,
        })
      );
      const { latitude, longitude } = position.coords;
      setCoords({ latitude, longitude });

      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json`
      );
      const data = await response.json();
      const address = data.address || {};
      setDistrict(
        address.state_district || address.county || address.city ||
        address.town || address.village || ""
      );
      setState(address.state || "");
    } catch (e) {
      // Not fatal, and not an error the farmer caused. They can type it.
      setError("Could not find your location. Please type your district.");
    } finally {
      setLocating(false);
    }
  };

  /** Step one, saved on its own so leaving halfway still keeps it. */
  const saveAbout = async (skipped) => {
    setError("");
    if (skipped) {
      setStep("farm");
      return;
    }
    setBusy(true);
    try {
      const result = await saveProfile({
        name: name.trim() || null,
        language: language || null,
        farmer_group: group || null,
        farmer_group_name: group && group !== "none" ? groupName.trim() || null : null,
      });
      // The account is updated but onboarding is not finished: step two is
      // still to come, so this must not call onboarded().
      if (result?.user && setUser) setUser(result.user);
      setStep("farm");
    } catch (e) {
      setError(e.message || "Could not save that. You can add it later.");
    } finally {
      setBusy(false);
    }
  };

  const saveFarm = async (skipped) => {
    setBusy(true);
    setError("");
    const parsedArea = parseFloat(area);
    try {
      const result = await saveProfile({
        district: skipped ? null : district.trim() || null,
        state: skipped ? null : state.trim() || null,
        latitude: skipped ? null : coords?.latitude ?? null,
        longitude: skipped ? null : coords?.longitude ?? null,
        crops: skipped ? null : crops,
        area: skipped || Number.isNaN(parsedArea) ? null : parsedArea,
        area_unit: skipped ? null : areaUnit,
        took_ms: Math.round(performance.now() - startedAt.current),
      });
      onboarded(result?.user);
    } catch (e) {
      setError(e.message || "Could not save that. You can add it later.");
      setBusy(false);
    }
  };

  const primary =
    "min-h-touch-lg w-full rounded-pill bg-leaf-600 text-base font-semibold text-white transition-colors hover:bg-leaf-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 focus-visible:ring-offset-2 disabled:bg-soil-300";
  const quiet = "min-h-touch text-sm text-soil-600 underline underline-offset-2";

  return (
    <section
      ref={topRef}
      aria-label={step === "about" ? "About you" : "Your farm"}
      className={embedded ? "mt-6 rounded-card bg-soil-50 px-4 py-6" : "min-h-screen bg-soil-50 px-4 py-8"}
    >
      <div className="mx-auto w-full max-w-[30rem]">
        <Progress at={step === "about" ? 1 : 2} />

        {step === "about" ? (
          <>
            <h2 className="mt-3 text-2xl font-bold text-soil-900">About you</h2>
            <p className="mt-2 text-sm text-soil-600">
              Number confirmed. Step 1 of 2 — everything here is optional.
            </p>

            <div className="mt-6 space-y-5 rounded-card border border-soil-200 bg-white p-5 shadow-card">
              <div>
                <label htmlFor="name" className="block text-sm font-semibold text-soil-900">
                  Your name
                </label>
                <input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="name"
                  maxLength={120}
                  placeholder="optional"
                  className={inputClass}
                />
              </div>

              <div>
                <span className="block text-sm font-semibold text-soil-900">
                  Language you prefer
                </span>
                <p className="mt-1 text-xs text-soil-500">
                  We always reply in the language you write in.
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {LANGUAGES.map(({ code, label }) => (
                    <Chip
                      key={code}
                      lang={code}
                      active={language === code}
                      aria-pressed={language === code}
                      onClick={() => setLanguage(language === code ? "" : code)}
                    >
                      {label}
                    </Chip>
                  ))}
                </div>
              </div>

              <div>
                <span className="block text-sm font-semibold text-soil-900">
                  Are you part of a farmer group?
                </span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {GROUPS.map(({ code, label }) => (
                    <Chip
                      key={code}
                      active={group === code}
                      aria-pressed={group === code}
                      onClick={() => setGroup(group === code ? "" : code)}
                    >
                      {label}
                    </Chip>
                  ))}
                </div>
                {group && group !== "none" && (
                  <>
                    <label htmlFor="group-name" className="mt-3 block text-sm text-soil-700">
                      Its name
                    </label>
                    <input
                      id="group-name"
                      value={groupName}
                      onChange={(e) => setGroupName(e.target.value)}
                      maxLength={120}
                      placeholder="optional"
                      className={inputClass}
                    />
                  </>
                )}
              </div>

              {error && <p className="text-sm text-red-700">{error}</p>}

              <button type="button" onClick={() => saveAbout(false)} disabled={busy} className={primary}>
                {busy ? "Saving…" : "Next: your farm"}
              </button>
            </div>

            <button
              type="button"
              onClick={() => saveAbout(true)}
              disabled={busy}
              className={`mx-auto mt-4 block ${quiet}`}
            >
              Skip
            </button>
          </>
        ) : (
          <>
            <h2 className="mt-3 text-2xl font-bold text-soil-900">Your farm</h2>
            <p className="mt-2 text-sm text-soil-600">
              Step 2 of 2. This is what makes answers fit your field — all optional.
            </p>

            <div className="mt-6 space-y-5 rounded-card border border-soil-200 bg-white p-5 shadow-card">
              <div>
                <label htmlFor="district" className="block text-sm font-semibold text-soil-900">
                  Your district
                </label>
                <p className="mt-1 text-xs text-soil-500">
                  Mandi prices are quoted per district, so this is the one that
                  changes answers most.
                </p>
                <div className="mt-2 flex gap-2">
                  <input
                    id="district"
                    value={district}
                    onChange={(e) => setDistrict(e.target.value)}
                    placeholder="Paschim Medinipur"
                    className="min-h-touch w-full min-w-0 flex-grow rounded-card border border-soil-300 bg-white px-3 text-base text-soil-900 outline-none focus:border-leaf-500 focus:ring-2 focus:ring-leaf-100 placeholder:text-soil-400"
                  />
                  <button
                    type="button"
                    onClick={useMyLocation}
                    disabled={locating}
                    aria-label="Use my location"
                    className="flex min-h-touch shrink-0 items-center gap-2 rounded-card border border-leaf-300 bg-leaf-50 px-3 text-sm text-leaf-800 disabled:opacity-60"
                  >
                    <FaLocationDot />
                    {locating ? "…" : "Locate"}
                  </button>
                </div>
                {state && (
                  <p className="mt-1 text-xs text-soil-500">State: {state}</p>
                )}
              </div>

              <div>
                <span className="block text-sm font-semibold text-soil-900">
                  What are you growing?
                </span>
                {user?.crops?.length > 0 && (
                  <p className="mt-1 text-xs text-soil-500">
                    Already marked from what you asked about. Tap to change.
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  {cropChoices.map((crop) => (
                    <Chip
                      key={crop}
                      active={crops.includes(crop)}
                      aria-pressed={crops.includes(crop)}
                      onClick={() => toggleCrop(crop)}
                    >
                      {crop}
                    </Chip>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="area" className="block text-sm font-semibold text-soil-900">
                  How much land?
                </label>
                <p className="mt-1 text-xs text-soil-500">
                  Doses are given per hectare. With this, we can tell you how much to
                  actually buy.
                </p>
                <div className="mt-2 flex gap-2">
                  <input
                    id="area"
                    value={area}
                    onChange={(e) => setArea(e.target.value.replace(/[^\d.]/g, ""))}
                    inputMode="decimal"
                    placeholder="2"
                    className="min-h-touch w-24 shrink-0 rounded-card border border-soil-300 bg-white px-3 text-base text-soil-900 outline-none focus:border-leaf-500 focus:ring-2 focus:ring-leaf-100 placeholder:text-soil-400"
                  />
                  <select
                    value={areaUnit}
                    onChange={(e) => setAreaUnit(e.target.value)}
                    aria-label="Unit of land area"
                    className="min-h-touch flex-grow rounded-card border border-soil-300 bg-white px-3 text-base text-soil-900 outline-none focus:border-leaf-500"
                  >
                    {UNITS.map((unit) => (
                      <option key={unit} value={unit}>{unit}</option>
                    ))}
                  </select>
                </div>
                {areaUnit === "bigha" && !state && (
                  // A bigha is a different area in nearly every state, so without one
                  // the backend refuses to convert rather than guessing. Say so here
                  // instead of silently dropping the number.
                  <p className="mt-2 text-xs text-grain-700">
                    A bigha differs by state. Add your district above so we can
                    convert it correctly.
                  </p>
                )}
              </div>

              {error && <p className="text-sm text-red-700">{error}</p>}

              <button type="button" onClick={() => saveFarm(false)} disabled={busy} className={primary}>
                {busy ? "Saving…" : "Save farm details"}
              </button>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <button type="button" onClick={() => setStep("about")} disabled={busy} className={quiet}>
                Back
              </button>
              <button type="button" onClick={() => saveFarm(true)} disabled={busy} className={quiet}>
                Skip for now
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

export default Onboarding;
