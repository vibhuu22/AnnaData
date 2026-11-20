import React, { useState } from 'react';
import { t } from '../../Config/uiLanguage';
import AnkurPicker from './AnkurPicker';
import { posesOf, useAvatar } from '../../Config/avatar';

/** A shared, fixed frame prevents layout shifts as Ankur changes expression. */
export default function Ankur({ pose = 'hello', className = 'h-20 w-20' }) {
  const avatar = useAvatar();
  const poses = posesOf(avatar);
  return <img src={poses?.[pose] || avatar.src} alt="" aria-hidden="true"
    width="512" height="512" className={`shrink-0 object-contain ${className}`} />;
}

/**
 * Ankur that can be tapped to choose another look: a small swap badge marks it,
 * and the picker opens over the screen. Used where Ankur greets the farmer.
 */
export function AnkurButton({ className = 'h-28 w-28', wrapClassName = '' }) {
  const [picking, setPicking] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setPicking(true)} aria-label={t('Change Ankur')} title={t('Change Ankur')}
        className={`relative shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf-600 ${wrapClassName}`}>
        <Ankur className={className} />
        <span aria-hidden="true" className="absolute bottom-1 right-1 grid h-7 w-7 place-items-center rounded-full bg-white text-leaf-700 shadow-sm ring-1 ring-soil-200">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 9h13l-3-3M20 15H7l3 3" /></svg>
        </span>
      </button>
      {picking && <AnkurPicker onClose={() => setPicking(false)} />}
    </>
  );
}
