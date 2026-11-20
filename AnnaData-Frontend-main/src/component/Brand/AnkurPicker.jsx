import React, { useEffect, useRef } from 'react';
import { t } from '../../Config/uiLanguage';
import { chooseAvatar, pickableAvatars, useAvatar } from '../../Config/avatar';

/**
 * Choose your Ankur: the looks drawn in every voice-mode pose, as large
 * pictures with the region's name. A tap picks one and closes; the choice is
 * kept on this phone. Closes on Escape, a tap outside, or the close button.
 */
export default function AnkurPicker({ onClose }) {
  const current = useAvatar();
  const firstRef = useRef(null);

  useEffect(() => {
    firstRef.current?.focus();
    const escape = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [onClose]);

  const pick = (id) => {
    chooseAvatar(id);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-soil-900/40 p-0 sm:items-center sm:p-4"
      onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="ankur-picker-title"
        className="glass max-h-[90vh] w-full max-w-[30rem] overflow-y-auto rounded-t-[28px] p-5 shadow-lift sm:rounded-[28px]">
        <div className="mb-1 flex items-center justify-between gap-3">
          <h2 id="ankur-picker-title" className="text-xl font-bold text-soil-900">{t('Choose your Ankur')}</h2>
          <button type="button" onClick={onClose} aria-label={t('Close')}
            className="grid h-touch w-touch place-items-center rounded-full text-soil-700 hover:bg-white/60">
            <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <p className="mb-4 text-sm text-soil-700">{t('Ankur keeps you company when you talk. More regional looks are coming.')}</p>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {pickableAvatars().map((a, i) => {
            const chosen = a.id === current.id;
            return (
              <li key={a.id}>
                <button ref={i === 0 ? firstRef : null} type="button" onClick={() => pick(a.id)} aria-pressed={chosen}
                  className={`flex w-full flex-col items-center gap-1 rounded-[20px] border-2 bg-white/70 p-2 pb-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 ${chosen ? 'border-leaf-600 bg-leaf-50' : 'border-transparent hover:border-soil-200'}`}>
                  <img src={a.src} alt="" width="512" height="512" className="h-28 w-28 object-contain" />
                  <span className="text-sm font-semibold text-soil-900">{t(a.region)}</span>
                  <span className="text-xs text-soil-600">{chosen ? t('Chosen') : t(a.look)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
