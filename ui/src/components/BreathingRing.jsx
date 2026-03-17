import React, { useState, useEffect, useRef } from 'react';

/**
 * BreathingRing — 17-second breath cycle visualization.
 * Matches core/breath.py exactly. No server sync — starts from zero at mount.
 *
 * 5 phases: inhale(3s), hold(3s), exhale(4s), hold_out(4s), rest(3s)
 */

const PHASES = [
  { name: 'inhale',   ms: 3000, index: 0 },
  { name: 'hold',     ms: 3000, index: 1 },
  { name: 'exhale',   ms: 4000, index: 2 },
  { name: 'hold_out', ms: 4000, index: 3 },
  { name: 'rest',     ms: 3000, index: 4 },
];
const CYCLE_MS = 17000;

function getPhase(elapsed) {
  const pos = elapsed % CYCLE_MS;
  let acc = 0;
  for (const phase of PHASES) {
    if (pos < acc + phase.ms) {
      return { ...phase, progress: (pos - acc) / phase.ms };
    }
    acc += phase.ms;
  }
  return { ...PHASES[4], progress: 1.0 };
}

export default function BreathingRing({ size = 180, onClick }) {
  const [phase, setPhase] = useState({ name: 'rest', progress: 0 });
  const startRef = useRef(performance.now());

  useEffect(() => {
    let raf;
    function tick() {
      const elapsed = performance.now() - startRef.current;
      setPhase(getPhase(elapsed));
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Ring expands on inhale, holds, contracts on exhale
  const breathScale = (() => {
    switch (phase.name) {
      case 'inhale':   return 0.85 + 0.15 * phase.progress;
      case 'hold':     return 1.0;
      case 'exhale':   return 1.0 - 0.15 * phase.progress;
      case 'hold_out': return 0.85;
      case 'rest':     return 0.85;
      default:         return 0.85;
    }
  })();

  // Opacity: brightest at exhale (when Jane responds), faintest at rest
  const breathOpacity = (() => {
    switch (phase.name) {
      case 'inhale':   return 0.3 + 0.3 * phase.progress;
      case 'hold':     return 0.6;
      case 'exhale':   return 0.6 + 0.2 * phase.progress;
      case 'hold_out': return 0.8 - 0.3 * phase.progress;
      case 'rest':     return 0.5 - 0.2 * phase.progress;
      default:         return 0.3;
    }
  })();

  const r = size / 2 - 8;
  const cx = size / 2;
  const cy = size / 2;

  return (
    <div
      onClick={onClick}
      className="cursor-pointer select-none"
      style={{ width: size, height: size }}
      title="breathe"
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Outer guide ring — always faint */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="var(--bark, #6b5b4e)"
          strokeWidth="1"
          opacity="0.12"
        />
        {/* Breathing ring */}
        <circle
          cx={cx} cy={cy}
          r={r * breathScale}
          fill="none"
          stroke="var(--leaf, #7a9a6d)"
          strokeWidth="2.5"
          opacity={breathOpacity}
          style={{ transition: 'r 100ms linear, opacity 100ms linear' }}
        />
        {/* Center dot — heartbeat */}
        <circle
          cx={cx} cy={cy}
          r={3}
          fill="var(--leaf, #7a9a6d)"
          opacity={breathOpacity * 0.8}
        />
      </svg>
    </div>
  );
}
