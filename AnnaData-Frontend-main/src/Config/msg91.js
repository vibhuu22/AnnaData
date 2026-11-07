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
const LOAD_TIMEOUT_MS = 20000;

/** Where MSG91 draws its captcha, when the widget has captcha on. */
export const CAPTCHA_ID = "msg91-captcha";

/** How many digits MSG91's codes have: the widget's "OTP Length" setting. */
export const CODE_LENGTH = parseInt(process.env.REACT_APP_MSG91_CODE_LENGTH || "6", 10);

export function msg91Enabled() {
  return Boolean(WIDGET_ID && TOKEN_AUTH);
}

let loading = null;

/**
 * Load MSG91's script once and start the widget. Resolves only when MSG91 has
 * accepted the widget id and token - not merely when its script has arrived:
 * a wrong token still defines sendOtp, then refuses everything
 * (AuthenticationFailure), which looked like a working widget. Rejects with
 * MSG91's own reason, or after LOAD_TIMEOUT_MS.
 */
export function loadWidget() {
  if (!msg91Enabled()) return Promise.reject(new Error("MSG91 is not configured"));
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    let settled = false;
    let poll = null;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearInterval(poll);
      if (error) reject(error);
      else resolve();
    };
    const timer = setTimeout(() => finish(new Error("MSG91 took too long to load")), LOAD_TIMEOUT_MS);
    // getWidgetData() is null until MSG91 has accepted the widget.
    const ready = () => {
      try {
        return Boolean(window.getWidgetData && window.getWidgetData());
      } catch (e) {
        return false;
      }
    };
    const start = () => {
      try {
        window.initSendOTP({
          widgetId: WIDGET_ID,
          tokenAuth: TOKEN_AUTH,
          exposeMethods: true,
          captchaRenderId: CAPTCHA_ID,
          // Per-call results come back through each method's own callbacks;
          // this one only hears whether the widget itself started.
          success: () => {},
          failure: (error) => {
            if (!ready()) finish(reason(error, "MSG91 refused the widget settings"));
          },
        });
      } catch (e) {
        finish(e);
        return;
      }
      poll = setInterval(() => ready() && finish(), 200);
    };
    if (typeof window.initSendOTP === "function") {
      if (ready()) finish();
      else start();
      return;
    }
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = start;
    script.onerror = () => finish(new Error("MSG91 could not be reached"));
    document.head.appendChild(script);
  }).catch((e) => {
    loading = null; // a later attempt starts afresh
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
