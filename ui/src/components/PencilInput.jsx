import React, { useState } from 'react';

/**
 * PencilInput — No-box input with pencil underline.
 * 20% opacity underline → 60% on focus.
 * Georgia for typed text, Ernie placeholder.
 */
export default function PencilInput({ value, onChange, onSubmit, placeholder = 'Write something...', disabled = false }) {
  const [focused, setFocused] = useState(false);

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey && onSubmit) {
      e.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="relative w-full">
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        disabled={disabled}
        placeholder={placeholder}
        rows={1}
        className={[
          'w-full bg-transparent font-journal text-ink resize-none',
          'outline-none border-0 py-2 px-0',
          'placeholder:font-ernie placeholder:opacity-faint',
          'transition-all duration-300',
        ].join(' ')}
        style={{
          borderBottom: `1px solid ${focused ? 'var(--pencil-active)' : 'var(--pencil)'}`,
          minHeight: '2.5rem',
          maxHeight: '12rem',
          overflow: 'auto',
        }}
      />
    </div>
  );
}
