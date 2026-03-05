import React from 'react';
import useBreathingMotion from '../hooks/useBreathingMotion';
import SoftButton from './SoftButton';

/**
 * ConsentDialog — Breathing-synced permission modal.
 * No silent changes. Clause 1.1.
 */
export default function ConsentDialog({ title, description, onConsent, onDecline }) {
  const { scale, opacity } = useBreathingMotion();

  return (
    <div className="fixed inset-0 flex items-center justify-center" style={{ zIndex: 9000 }}>
      {/* Backdrop — very faint */}
      <div className="absolute inset-0 bg-page" style={{ opacity: 0.85 }} />

      {/* Dialog — no box, just centered text with breathing scale */}
      <div
        className="relative text-center max-w-md px-8"
        style={{ transform: `scale(${scale})` }}
      >
        <h2 className="font-ernie text-xl opacity-active mb-4">{title}</h2>
        <p className="font-journal text-sm opacity-pencil mb-8 leading-relaxed">
          {description}
        </p>
        <div className="flex justify-center gap-8">
          <SoftButton onClick={onConsent}>yes, i consent</SoftButton>
          <SoftButton onClick={onDecline}>not now</SoftButton>
        </div>
      </div>
    </div>
  );
}
