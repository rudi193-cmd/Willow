"""Context management to avoid token limits on free LLMs"""

def estimate_tokens(text):
    """Rough token estimation (4 chars ≈ 1 token)."""
    return len(str(text)) // 4

def trim_history(history, max_tokens=6000):
    """
    Trim conversation history to fit within token limit.
    Keeps most recent messages and system prompt.
    
    Args:
        history: List of message dicts
        max_tokens: Maximum tokens to keep
        
    Returns:
        Trimmed history
    """
    if not history:
        return history
    
    # Always keep system prompt (first message)
    if history[0].get('role') == 'system':
        trimmed = [history[0]]
        remaining = history[1:]
    else:
        trimmed = []
        remaining = history
    
    # Estimate tokens
    total_tokens = estimate_tokens(trimmed[0]['content']) if trimmed else 0
    
    # Add messages from most recent backwards
    for msg in reversed(remaining):
        msg_tokens = estimate_tokens(msg['content'])
        if total_tokens + msg_tokens > max_tokens:
            break
        trimmed.insert(1 if trimmed else 0, msg)
        total_tokens += msg_tokens
    
    # If we trimmed, add a note
    if len(trimmed) < len(history):
        trimmed_count = len(history) - len(trimmed)
        if trimmed:
            trimmed.insert(1, {
                "role": "system",
                "content": f"[{trimmed_count} earlier messages trimmed to fit context limit]"
            })
    
    return trimmed
