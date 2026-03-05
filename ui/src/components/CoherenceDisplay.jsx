import React from 'react';
import useBreathingMotion from '../hooks/useBreathingMotion';

/**
 * CoherenceDisplay — Breathing ΔE indicator.
 * Blue (#4a90d9) for stable/decaying, gold (#d4a017) for regenerative.
 * Pulses with 15s breathing cycle.
 */
export default function CoherenceDisplay({ coherence }) {
  const { scale, opacity } = useBreathingMotion();

  if (!coherence) return null;

  const deltaE = coherence.delta_e || 0;
  const ci = coherence.coherence_index || 0;
  const state = coherence.state || 'stable';
  const isRegen = state === 'regenerative';
  const arrow = isRegen ? '\u2191' : state === 'decaying' ? '\u2193' : '\u2192';

  return (
    <div
      className="font-ernie text-sm opacity-pencil aionic-fade cursor-default select-none"
      style={{
        transform: `scale(${scale})`,
        color: isRegen ? 'var(--coherence-regen)' : 'var(--coherence-stable)',
      }}
      title={`Coherence Index: ${ci.toFixed(2)} | State: ${state}`}
    >
      {'\u0394'}E: {deltaE >= 0 ? '+' : ''}{deltaE.toFixed(4)} {arrow}
    </div>
  );
}
