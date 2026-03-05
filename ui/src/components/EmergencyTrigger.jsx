import React, { useState } from 'react';

/**
 * EmergencyTrigger — Safety net. Always available, never disabled.
 * Bottom-left, 5% opacity → 20% on hover.
 * Brightens to 60% when emergency detected.
 * z-index: 9999
 */
export default function EmergencyTrigger({ isDistressed = false }) {
  const [hovered, setHovered] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const showExpanded = expanded || isDistressed;

  let opacityClass = 'opacity-ghost';           // 5%
  if (isDistressed) opacityClass = 'opacity-active';  // 60%
  else if (hovered) opacityClass = 'opacity-pencil';  // 20%

  return (
    <div
      className={`fixed bottom-4 left-4 font-ernie transition-opacity duration-300 ${opacityClass}`}
      style={{ zIndex: 9999 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); if (!isDistressed) setExpanded(false); }}
      onClick={() => setExpanded(!expanded)}
    >
      {showExpanded ? (
        <div className="text-sm space-y-1">
          <div className="font-bold">You are not alone.</div>
          <a href="tel:988" className="block underline">988 — Crisis Lifeline</a>
          <a href="tel:911" className="block underline">911 — Emergency</a>
          <a href="https://988lifeline.org/chat/" target="_blank" rel="noopener" className="block underline">
            988 Online Chat
          </a>
        </div>
      ) : (
        <span className="text-xs select-none">safe space</span>
      )}
    </div>
  );
}
