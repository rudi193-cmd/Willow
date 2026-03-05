import React from 'react';

/**
 * MessageBubble — No bubbles. Just typography and breathing space.
 * User: Georgia, full opacity.
 * Assistant: Ernie handwriting, 60% opacity.
 * Tier badge: tiny Ernie at 15%.
 */
export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className="my-6">
      {isUser ? (
        <p className="font-journal text-ink leading-relaxed whitespace-pre-wrap">
          {message.text}
        </p>
      ) : (
        <>
          <p className="font-ernie text-ink opacity-active leading-relaxed whitespace-pre-wrap text-lg">
            {message.text}
            {!message.text && (
              <span className="opacity-pencil animate-pulse">...</span>
            )}
          </p>
          {message.tier && (
            <span className="font-ernie text-xs opacity-faint mt-1 block">
              tier {message.tier.number} · {message.tier.desc}
            </span>
          )}
        </>
      )}
    </div>
  );
}
