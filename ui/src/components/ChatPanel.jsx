import React, { useRef, useEffect, useState } from 'react';
import MessageBubble from './MessageBubble';
import PencilInput from './PencilInput';
import CoherenceDisplay from './CoherenceDisplay';

/**
 * ChatPanel — Message list + PencilInput + streaming display.
 * No containers. Messages separated by breathing space.
 */
export default function ChatPanel({ messages, isStreaming, coherence, onSend, atLimit, onCheckEmergency }) {
  const [input, setInput] = useState('');
  const scrollRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  function handleSubmit() {
    const text = input.trim();
    if (!text || isStreaming || atLimit) return;
    if (onCheckEmergency) onCheckEmergency(text);
    onSend(text);
    setInput('');
  }

  function handleChange(value) {
    setInput(value);
  }

  return (
    <div className="flex flex-col h-full journal-page">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto journal-content py-6">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <p className="font-ernie text-lg opacity-faint select-none">
              begin when you're ready
            </p>
          </div>
        )}

        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Pencil-line divider between messages and input */}
        {messages.length > 0 && <div className="pencil-line-faint my-4" />}
      </div>

      {/* Input area — bottom */}
      <div className="journal-content pb-6 pt-2">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <PencilInput
              value={input}
              onChange={handleChange}
              onSubmit={handleSubmit}
              placeholder={atLimit ? 'session complete (314 exchanges)' : 'write...'}
              disabled={isStreaming || atLimit}
            />
          </div>
          <CoherenceDisplay coherence={coherence} />
        </div>

        {/* Streaming indicator */}
        {isStreaming && (
          <span className="font-ernie text-xs opacity-faint mt-1 block animate-pulse">
            listening...
          </span>
        )}
      </div>
    </div>
  );
}
