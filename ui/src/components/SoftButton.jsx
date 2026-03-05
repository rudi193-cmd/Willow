import React from 'react';

/**
 * SoftButton — Ernie font, 20% opacity → 60% on hover.
 * No background, no border. Pure typography.
 */
export default function SoftButton({ children, onClick, className = '', active = false }) {
  return (
    <button
      onClick={onClick}
      className={[
        'font-ernie bg-transparent border-0 cursor-pointer',
        'transition-opacity duration-300',
        active ? 'opacity-active' : 'opacity-pencil hover:opacity-active active:opacity-active',
        className,
      ].join(' ')}
    >
      {children}
    </button>
  );
}
