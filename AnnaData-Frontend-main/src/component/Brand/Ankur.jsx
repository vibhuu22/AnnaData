import React from 'react';
import { currentAvatar, posesOf } from '../../Config/avatar';

/** A shared, fixed frame prevents layout shifts as Ankur changes expression. */
export default function Ankur({ pose = 'hello', className = 'h-20 w-20' }) {
  const avatar = currentAvatar();
  const poses = posesOf(avatar);
  return <img src={poses?.[pose] || avatar.src} alt="" aria-hidden="true"
    width="512" height="512" className={`shrink-0 object-contain ${className}`} />;
}
