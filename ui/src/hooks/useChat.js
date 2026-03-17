import { useState, useCallback, useRef } from 'react';

const PI_LIMIT = 314;

/**
 * Chat hook — Agent-routed for consumer personas, SSE fallback for UTETY.
 * π harmonic limit: 314 exchanges per session.
 */
export default function useChat() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [exchangeCount, setExchangeCount] = useState(0);
  const [coherence, setCoherence] = useState(null);
  const historyRef = useRef([]);

  const sendMessage = useCallback(async (prompt, persona = 'Willow') => {
    if (!prompt.trim() || isStreaming) return;
    if (exchangeCount >= PI_LIMIT) return;

    // Add user message
    const userMsg = { id: Date.now(), role: 'user', text: prompt, timestamp: new Date().toISOString() };
    const assistantMsg = { id: Date.now() + 1, role: 'assistant', text: '', timestamp: new Date().toISOString(), tier: null, persona };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    // Track conversation history for agent context
    historyRef.current.push({ role: 'user', content: prompt });

    // Consumer personas route through agent engine (tool access, entity lookup)
    const isConsumer = persona === 'Shiva_Consumer' || persona.startsWith('NASA_');

    try {
      if (isConsumer) {
        await _sendAgentChat(prompt, persona, historyRef, setMessages, setCoherence);
      } else {
        await _sendSSEChat(prompt, persona, setMessages, setCoherence);
      }
      setExchangeCount(prev => prev + 1);
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === 'assistant') {
          last.text = "I'm having a little trouble connecting right now. Could you try again in a moment?";
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
    historyRef.current = [];
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


/**
 * Agent-routed chat (JSON, not SSE).
 * Goes through agent_engine.chat() → tool access, entity lookup, knowledge search.
 */
async function _sendAgentChat(prompt, persona, historyRef, setMessages, setCoherence) {
  // Map consumer persona to agent name
  const agentName = persona === 'Shiva_Consumer' ? 'shiva' : persona.toLowerCase().replace('nasa_', 'nasa_');

  const response = await fetch(`/api/agents/chat/${agentName}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: prompt,
      conversation_history: historyRef.current,
    }),
  });

  if (!response.ok) {
    throw new Error(`Agent responded ${response.status}`);
  }

  const data = await response.json();
  const text = data.response || data.error || "I wasn't able to form a response. Could you try again?";

  // Track assistant response in history
  historyRef.current.push({ role: 'assistant', content: text });

  // Update assistant message with full response
  setMessages(prev => {
    const updated = [...prev];
    const last = updated[updated.length - 1];
    if (last && last.role === 'assistant') {
      last.text = text;
    }
    return updated;
  });
}


/**
 * SSE streaming chat (legacy path for UTETY personas).
 * Goes through local_api.process_smart_stream().
 */
async function _sendSSEChat(prompt, persona, setMessages, setCoherence) {
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
      if (line.startsWith('event: coherence') || line.startsWith('event: done')) continue;
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
          // Not JSON — text chunk
        }

        // Append text chunk to assistant message
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant') {
            const tierMatch = data.match(/^\[Tier (\d+): ([^\]]+)\]/);
            if (tierMatch && !last.tier) {
              last.tier = { number: parseInt(tierMatch[1]), desc: tierMatch[2] };
              const remainder = data.replace(tierMatch[0], '').replace(/^\n/, '');
              last.text += remainder;
            } else if (data.startsWith('[ERROR]')) {
              last.text += "I'm having a little trouble connecting right now. Could you try again in a moment?";
            } else {
              last.text += data;
            }
          }
          return updated;
        });
      }
    }
  }
}
