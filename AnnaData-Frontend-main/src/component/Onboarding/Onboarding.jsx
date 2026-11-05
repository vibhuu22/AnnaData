import React, { useContext, useEffect, useRef, useState } from "react";
import { Auth } from "../../Context/AuthProvider";
import { saveProfile } from "../../Config/session";
import {
  BackLink,
  Chip,
  FlowScreen,
  StepBar,
  fieldClass,
  maskPhone,
  primaryButton,
  textButton,
} from "../Flow/ui";

/**
 * The sign-up questions, after the number is confirmed.
 *
 * TWO SHORT FULL SCREENS, About you and Your farm, laid out as in the
 * wireframes: Skip at the top, one primary button pinned at the bottom. This was one screen, on the
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

const CROPS = ["wheat", "rice", "cotton", "mustard", "potato", "sugarcane", "maize", "soybean"];
const UNITS = ["acre", "bigha", "hectare", "guntha"];

// Profile `language` values, each in its own script so a farmer can find
// theirs without reading English.
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

const title = (crop) => crop.charAt(0).toUpperCase() + crop.slice(1);

/**
 * @param onDone   called when the farmer finishes, skips, or (when editing)
 *                 leaves - the flow returns them to the conversation
 * @param editing  a farmer changing details they already gave, from the home
 *                 screen's "Edit": leaving does not mark anything as skipped
 */
function Onboarding({ onDone, editing = false }) {
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
  const [extraCrops, setExtraCrops] = useState(
    (user?.crops || []).filter((c) => !CROPS.includes(c))
  );
  const [addingCrop, setAddingCrop] = useState(false);
  const [newCrop, setNewCrop] = useState("");
  const [area, setArea] = useState("");
  const [areaUnit, setAreaUnit] = useState(user?.area_unit || "acre");
  const [locating, setLocating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Wall-clock from the moment the form is on screen to the moment it is sent.
  const startedAt = useRef(performance.now());
  useEffect(() => {
    startedAt.current = performance.now();
  }, []);

  useEffect(() => {
    window.scrollTo?.(0, 0);
  }, [step]);

  const askedAbout = (user?.crops || []).filter((c) => crops.includes(c));

  const toggleCrop = (crop) =>
    setCrops((prev) => (prev.includes(crop) ? prev.filter((c) => c !== crop) : [...prev, crop]));

  const addCrop = () => {
    const crop = newCrop.trim().toLowerCase();
    if (crop) {
      if (!CROPS.includes(crop) && !extraCrops.includes(crop)) setExtraCrops((prev) => [...prev, crop]);
      if (!crops.includes(crop)) setCrops((prev) => [...prev, crop]);
    }
    setNewCrop("");
    setAddingCrop(false);
  };

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
        address.state_district || address.county || address.city || address.town || address.village || ""
      );
      setState(address.state || "");
    } catch (e) {
      // Not fatal, and not an error the farmer caused. They can type it.
      setError("Could not find your location. Please type your district.");
    } finally {
      setLocating(false);
    }
  };

  /** Leave without filling anything in. */
  const skipAll = async () => {
    if (editing) {
      onDone?.();
      return;
    }
    setBusy(true);
    try {
      // Recorded, so the farmer is not asked again on their next visit.
      const result = await saveProfile({ took_ms: Math.round(performance.now() - startedAt.current) });
      onboarded(result?.user);
    } catch (e) {
      onboarded();
    }
    onDone?.();
  };

  /** Step one, saved on its own so leaving halfway still keeps it. */
  const saveAbout = async () => {
    setBusy(true);
    setError("");
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

  const saveFarm = async () => {
    setBusy(true);
    setError("");
    const parsedArea = parseFloat(area);
    try {
      const result = await saveProfile({
        district: district.trim() || null,
        state: state.trim() || null,
        latitude: coords?.latitude ?? null,
        longitude: coords?.longitude ?? null,
        crops,
        area: Number.isNaN(parsedArea) ? null : parsedArea,
        area_unit: Number.isNaN(parsedArea) ? null : areaUnit,
        took_ms: Math.round(performance.now() - startedAt.current),
      });
      onboarded(result?.user);
      onDone?.();
    } catch (e) {
      setError(e.message || "Could not save that. You can add it later.");
      setBusy(false);
    }
  };

  const skip = (
    <button type="button" onClick={skipAll} disabled={busy} className={textButton}>
      {editing ? "Close" : "Skip"}
    </button>
  );
  const errorLine = error && (
    <p role="alert" className="text-sm text-red-700">
      {error}
    </p>
  );

  if (step === "about") {
    const masked = maskPhone(user?.phone || user?.user_id);
    return (
      <FlowScreen
        label="About you"
        top={
          <>
            <div className="text-sm text-soil-600">
              {editing ? "Your details" : `Number confirmed${masked ? ` · ${masked}` : ""}`}
            </div>
            {skip}
          </>
        }
        actions={
          <button type="button" onClick={saveAbout} disabled={busy} className={primaryButton}>
            {busy ? "Saving…" : "Next: your farm"}
          </button>
        }
      >
        <StepBar step={1} />
        <div>
          <h1 className="text-2xl font-bold leading-tight">About you</h1>
          <p className="mt-2 text-sm text-soil-700">Everything here is optional.</p>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="name" className="text-sm font-semibold">
            Your name
          </label>
          <input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            maxLength={120}
            placeholder="e.g. Ramesh Kumar"
            className={`${fieldClass} h-[52px]`}
          />
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm font-semibold">Language you prefer</span>
          <div className="flex flex-wrap gap-2">
            {LANGUAGES.map(({ code, label }) => (
              <Chip
                key={code}
                lang={code}
                active={language === code}
                onClick={() => setLanguage(language === code ? "" : code)}
              >
                {label}
              </Chip>
            ))}
          </div>
          <p className="text-xs text-soil-600">We always reply in the language you write in.</p>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm font-semibold">Are you part of a farmer group?</span>
          <div className="flex flex-wrap gap-2">
            {GROUPS.map(({ code, label }) => (
              <Chip key={code} active={group === code} onClick={() => setGroup(group === code ? "" : code)}>
                {label}
              </Chip>
            ))}
          </div>
          {group && group !== "none" && (
            <>
              <label htmlFor="group-name" className="sr-only">
                Group name
              </label>
              <input
                id="group-name"
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                maxLength={120}
                placeholder="Group name (optional)"
                className={`${fieldClass} h-12`}
              />
            </>
          )}
        </div>
        {errorLine}
      </FlowScreen>
    );
  }

  return (
    <FlowScreen
      label="Your farm"
      top={
        <>
          <BackLink onClick={() => setStep("about")}>Back</BackLink>
          {skip}
        </>
      }
      actions={
        <button type="button" onClick={saveFarm} disabled={busy} className={primaryButton}>
          {busy ? "Saving…" : "Save farm details"}
        </button>
      }
    >
      <StepBar step={2} />
      <div>
        <h1 className="text-2xl font-bold leading-tight">Your farm</h1>
        <p className="mt-2 text-sm text-soil-700">
          Optional. It lets us answer for your district and crops without asking every time.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="district" className="text-sm font-semibold">
          District
        </label>
        <div className="flex gap-2">
          <input
            id="district"
            value={district}
            onChange={(e) => setDistrict(e.target.value)}
            placeholder="e.g. Paschim Medinipur"
            className={`${fieldClass} h-12 flex-1`}
          />
          <button
            type="button"
            onClick={useMyLocation}
            disabled={locating}
            className="flex h-12 shrink-0 items-center gap-1.5 rounded-[10px] border-[1.5px] border-soil-400 bg-white px-3 text-sm font-semibold text-soil-900 disabled:opacity-60"
          >
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="11" r="3" />
              <path d="M12 21s-7-6.5-7-11a7 7 0 0 1 14 0c0 4.5-7 11-7 11z" />
            </svg>
            {locating ? "Finding…" : "Use location"}
          </button>
        </div>
        {state && <p className="text-xs text-soil-600">State: {state}</p>}
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-semibold">What are you growing?</span>
        <div className="flex flex-wrap gap-2">
          {[...CROPS, ...extraCrops].map((crop) => (
            <Chip key={crop} active={crops.includes(crop)} onClick={() => toggleCrop(crop)}>
              {title(crop)}
            </Chip>
          ))}
          {!addingCrop && (
            <Chip active={false} onClick={() => setAddingCrop(true)}>
              + Other
            </Chip>
          )}
        </div>
        {addingCrop && (
          <div className="flex gap-2">
            <label htmlFor="new-crop" className="sr-only">
              Another crop
            </label>
            <input
              id="new-crop"
              value={newCrop}
              autoFocus
              onChange={(e) => setNewCrop(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCrop())}
              maxLength={40}
              placeholder="e.g. chilli"
              className={`${fieldClass} h-12 flex-1`}
            />
            <button type="button" onClick={addCrop} className="h-12 shrink-0 rounded-[10px] bg-leaf-600 px-4 text-sm font-semibold text-white">
              Add
            </button>
          </div>
        )}
        {askedAbout.length > 0 && (
          <p className="text-xs text-soil-600">
            {askedAbout.map(title).join(", ")} {askedAbout.length === 1 ? "is" : "are"} already picked from the
            question you asked.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="area" className="text-sm font-semibold">
          How much land?
        </label>
        <div className="flex gap-2">
          <input
            id="area"
            value={area}
            onChange={(e) => setArea(e.target.value.replace(/[^\d.]/g, ""))}
            inputMode="decimal"
            placeholder="2"
            className={`${fieldClass.replace("w-full ", "")} h-12 w-24 shrink-0`}
          />
          <label htmlFor="unit" className="sr-only">
            Unit of land area
          </label>
          <select
            id="unit"
            value={areaUnit}
            onChange={(e) => setAreaUnit(e.target.value)}
            className={`${fieldClass} h-12 flex-1`}
          >
            {UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
        </div>
        {areaUnit === "bigha" && (
          // A bigha is a different area in nearly every state, so without one
          // the backend refuses to convert rather than guessing.
          <p className="text-xs text-soil-600">
            A bigha is a different size in each state — we use your district to convert it.
          </p>
        )}
      </div>
      {errorLine}
    </FlowScreen>
  );
}

export default Onboarding;
