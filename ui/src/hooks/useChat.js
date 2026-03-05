import { useState, useCallback, useRef } from 'react';

const PI_LIMIT = 314;

/**
 * Chat hook — SSE streaming with 314 exchange π harmonic limit.
 */
export default function useChat() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [exchangeCount, setExchangeCount] = useState(0);
  const [coherence, setCoherence] = useState(null);
  const abortRef = useRef(null);

  const sendMessage = useCallback(async (prompt, persona = 'Willow') => {
    if (!prompt.trim() || isStreaming) return;
    if (exchangeCount >= PI_LIMIT) return;

    // Add user message
    const userMsg = { id: Date.now(), role: 'user', text: prompt, timestamp: new Date().toISOString() };
    const assistantMsg = { id: Date.now() + 1, role: 'assistant', text: '', timestamp: new Date().toISOString(), tier: null, persona };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, persona }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event: coherence')) {
            // Next data line has coherence JSON
            continue;
          }
          if (line.startsWith('event: done')) {
            continue;
          }
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            // Try parsing as coherence JSON
            try {
              const parsed = JSON.parse(data);
              if (parsed.coherence_index !== undefined) {
                setCoherence(parsed);
                continue;
              }
            } catch {
              // Not JSON — it's a text chunk
            }

            // Append text chunk to assistant message
            setMessages(prev => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === 'assistant') {
                // Detect tier from first chunk (e.g., "[Tier 2: General conversation]")
                const tierMatch = data.match(/^\[Tier (\d+): ([^\]]+)\]/);
                if (tierMatch && !last.tier) {
                  last.tier = { number: parseInt(tierMatch[1]), desc: tierMatch[2] };
                  // Don't append the tier line to visible text
                  const remainder = data.replace(tierMatch[0], '').replace(/^\n/, '');
                  last.text += remainder;
                } else {
                  last.text += data;
                }
              }
              return updated;
            });
          }
        }
      }

      setExchangeCount(prev => prev + 1);
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === 'assistant') {
          last.text = `[Connection error: ${err.message}]`;
        }
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  }, [isStreaming, exchangeCount]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setExchangeCount(0);
    setCoherence(null);
  }, []);

  return {
    messages,
    isStreaming,
    exchangeCount,
    piLimit: PI_LIMIT,
    coherence,
    sendMessage,
    clearMessages,
    atLimit: exchangeCount >= PI_LIMIT,
  };
}
