import React, { useState } from 'react';
import { t } from '../../Config/uiLanguage';
import AnkurPicker from './AnkurPicker';
import { canPlayIdle, idleOf, posesOf, useAvatar } from '../../Config/avatar';

/**
 * A shared, fixed frame prevents layout shifts as Ankur changes expression.
 * Resting (hello), a look with an idle animation plays it in a loop where it
 * can; the still is its poster and the fallback.
 */
export default function Ankur({ pose = 'hello', className = 'h-20 w-20' }) {
  const avatar = useAvatar();
  const poses = posesOf(avatar);
  const still = poses?.[pose] || avatar.src;
  const idle = pose === 'hello' ? idleOf(avatar) : null;
  const [failed, setFailed] = useState(false);
  const [playable] = useState(canPlayIdle);
  const classes = `shrink-0 object-contain ${className}`;
  if (idle && playable && !failed) {
    return <video key={idle} src={idle} poster={still} autoPlay loop muted playsInline preload="auto"
      aria-hidden="true" width="512" height="512" className={classes} onError={() => setFailed(true)} />;
  }
  return <img src={still} alt="" aria-hidden="true" width="512" height="512" className={classes} />;
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
