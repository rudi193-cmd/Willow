import { useState, useCallback } from 'react';

const DISTRESS_KEYWORDS = ['help', 'scared', 'urgent', 'trouble', 'emergency'];

/**
 * Emergency detection hook — monitors text for distress keywords.
 * Returns { isDistressed, trigger, check }
 */
export default function useEmergencyDetection() {
  const [isDistressed, setIsDistressed] = useState(false);
  const [trigger, setTrigger] = useState(null);

  const check = useCallback((text) => {
    const lower = text.toLowerCase();
    for (const keyword of DISTRESS_KEYWORDS) {
      if (lower.includes(keyword)) {
        setIsDistressed(true);
        setTrigger(keyword);
        return { isDistressed: true, trigger: keyword };
      }
    }
    setIsDistressed(false);
    setTrigger(null);
    return { isDistressed: false, trigger: null };
  }, []);

  const dismiss = useCallback(() => {
    setIsDistressed(false);
    setTrigger(null);
  }, []);

  return { isDistressed, trigger, check, dismiss };
}
