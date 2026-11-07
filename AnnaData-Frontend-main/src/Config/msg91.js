/**
 * Sign-in codes through MSG91's OTP widget, in AnnaData's own screens.
 *
 * MSG91 calls this "Web SDK for custom UI": its script puts sendOtp, retryOtp
 * and verifyOtp on `window` (exposeMethods: true) and shows no popup of its
 * own. A verified code gives the browser an access token, which proves nothing
 * by itself - the backend asks MSG91 about it (/auth/verify-widget) and signs
 * in the number MSG91 says it verified.
 *
 * Used only when both values below are set at build time (Render's
 * environment). Without them, or if MSG91's script cannot be loaded, sign-in
 * uses AnnaData's own codes as before. The widget id and token are meant to
 * sit in the browser; MSG91's secret auth key never does.
 */

const WIDGET_ID = process.env.REACT_APP_MSG91_WIDGET_ID || "";
const TOKEN_AUTH = process.env.REACT_APP_MSG91_TOKEN_AUTH || "";
const SCRIPT = "https://verify.msg91.com/otp-provider.js";
const LOAD_TIMEOUT_MS = 10000;

/** Where MSG91 draws its captcha, when the widget has captcha on. */
export const CAPTCHA_ID = "msg91-captcha";

/** How many digits MSG91's codes have: the widget's "OTP Length" setting. */
export const CODE_LENGTH = parseInt(process.env.REACT_APP_MSG91_CODE_LENGTH || "6", 10);

export function msg91Enabled() {
  return Boolean(WIDGET_ID && TOKEN_AUTH);
}

let loading = null;

/** Load MSG91's script once and start the widget. Rejects if it cannot. */
export function loadWidget() {
  if (!msg91Enabled()) return Promise.reject(new Error("MSG91 is not configured"));
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    if (typeof window.sendOtp === "function") return resolve();
    const timer = setTimeout(() => reject(new Error("MSG91 did not load")), LOAD_TIMEOUT_MS);
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = () => {
      try {
        window.initSendOTP({
          widgetId: WIDGET_ID,
          tokenAuth: TOKEN_AUTH,
          exposeMethods: true,
          captchaRenderId: CAPTCHA_ID,
          // Results come back through each method's own callbacks; listening
          // here as well would deliver every event twice.
          success: () => {},
          failure: () => {},
        });
        clearTimeout(timer);
        resolve();
      } catch (e) {
        clearTimeout(timer);
        reject(e);
      }
    };
    script.onerror = () => {
      clearTimeout(timer);
      reject(new Error("MSG91 could not be reached"));
    };
    document.head.appendChild(script);
  }).catch((e) => {
    loading = null; // try again next time
    throw e;
  });
  return loading;
}

function reason(error, fallback) {
  const said = error && (error.message || error.msg || (typeof error === "string" ? error : ""));
  return new Error(said && typeof said === "string" ? said : fallback);
}

function call(name, args, fallback) {
  return new Promise((resolve, reject) => {
    const method = window[name];
    if (typeof method !== "function") return reject(new Error(fallback));
    method(...args, (data) => resolve(data), (error) => reject(reason(error, fallback)));
    return undefined;
  });
}

/** Send a code to a 10-digit Indian mobile number. */
export async function sendCode(digits) {
  await loadWidget();
  return call("sendOtp", [`91${digits}`], "Could not send the code.");
}

/** Send the code again, on the widget's default channel order. */
export async function resendCode() {
  await loadWidget();
  // null = the channels in the widget's own settings (SMS, then voice).
  return call("retryOtp", [null], "Could not send the code again.");
}

/** Check a code; resolves to MSG91's access token for the backend. */
export async function verifyCode(code) {
  await loadWidget();
  const data = await call("verifyOtp", [code], "That code did not work.");
  const token = data && (data.message || data.token || data["access-token"]);
  if (!token) throw new Error("That code could not be confirmed.");
  return token;
}
