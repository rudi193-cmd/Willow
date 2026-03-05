import { useState, useEffect, useRef } from 'react';

const INHALE_MS = 7000;
const EXHALE_MS = 8000;
const CYCLE_MS = INHALE_MS + EXHALE_MS;
const MIN_SCALE = 1.0;
const MAX_SCALE = 1.02;
const MIN_OPACITY = 0.20;
const MAX_OPACITY = 0.25;

/**
 * Breathing motion hook — 15s cycle (7s inhale, 8s exhale).
 * Returns { phase, scale, opacity, isExhaling }
 *
 * Used by: CoherenceDisplay, ConsentDialog, save timing.
 */
export default function useBreathingMotion() {
  const [state, setState] = useState({
    phase: 'inhale',
    scale: MIN_SCALE,
    opacity: MIN_OPACITY,
    isExhaling: false,
  });
  const rafRef = useRef(null);
  const startRef = useRef(Date.now());

  useEffect(() => {
    function tick() {
      const elapsed = (Date.now() - startRef.current) % CYCLE_MS;
      let phase, progress;

      if (elapsed < INHALE_MS) {
        phase = 'inhale';
        progress = elapsed / INHALE_MS;
      } else {
        phase = 'exhale';
        progress = 1 - (elapsed - INHALE_MS) / EXHALE_MS;
      }

      setState({
        phase,
        scale: MIN_SCALE + (MAX_SCALE - MIN_SCALE) * progress,
        opacity: MIN_OPACITY + (MAX_OPACITY - MIN_OPACITY) * progress,
        isExhaling: phase === 'exhale',
      });

      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return state;
}
