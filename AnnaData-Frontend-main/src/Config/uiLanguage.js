import { useSyncExternalStore } from 'react';
import hindi from './uiHindi.json';

const KEY = 'annadata.uiLanguage';
const listeners = new Set();
export function initialLanguage() {
  try {
    const saved = window.localStorage.getItem(KEY);
    if (saved === 'hi' || saved === 'en') return saved;
  } catch { /* Private browsing still supports a preference for this visit. */ }
  return /^hi(?:-|$)/i.test(navigator.language || '') ? 'hi' : 'en';
}
let language = initialLanguage();
export const uiLocale = () => language === 'hi' ? 'hi-IN' : 'en-IN';
export function setUiLanguage(next) {
  if (next !== 'hi' && next !== 'en') return;
  language = next;
  try { window.localStorage.setItem(KEY, next); } catch { /* Visit only. */ }
  document.documentElement.lang = next;
  listeners.forEach((listener) => listener());
}
const subscribe = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };
export function useUiLanguage() {
  return useSyncExternalStore(subscribe, () => language, () => 'en');
}
/** UI copy only. Never pass farmer messages, news headlines or answers here. */
export function t(key, values = {}) {
  const text = language === 'hi' && Object.prototype.hasOwnProperty.call(hindi, key) ? hindi[key] : key;
  return text.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
}
