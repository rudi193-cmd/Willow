import React from 'react';
import ConsentDialog from './ConsentDialog';

/**
 * DeeperLayerGate — "Show deeper layer?" consent gate.
 * Explicit consent required before AI analysis crosses from Source to Bridge ring.
 * Consent is volatile — resets each session.
 */
export default function DeeperLayerGate({ onConsent, onDecline }) {
  return (
    <ConsentDialog
      title="Show deeper layer?"
      description="Willow has detected a pattern it could explore further. This would use AI analysis on your recent input. You can always decline — your words remain yours."
      onConsent={onConsent}
      onDecline={onDecline}
    />
  );
}
