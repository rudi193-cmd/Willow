"""
Context Check - Query RAG before architectural decisions

Use this before making changes to core systems.

GOVERNANCE: Prevents architectural drift by checking past decisions.
CHECKSUM: ΔΣ=42
"""

from core import conversation_rag

def check_context(topic: str, threshold: float = 0.25) -> str:
    """
    Query RAG for relevant context on a topic.
    
    Args:
        topic: What you're about to change (e.g., "Willow routing")
        threshold: Minimum similarity to report (default: 0.25)
    
    Returns:
        Context string if found, empty string otherwise
    """
    results = conversation_rag.query(topic, top_k=3)
    
    if not results:
        return ""
    
    relevant = [r for r in results if r["similarity"] > threshold]
    
    if not relevant:
        return ""
    
    context_parts = []
    context_parts.append(f"[RAG CONTEXT] Found {len(relevant)} relevant past discussions:")
    
    for i, result in enumerate(relevant, 1):
        similarity_pct = int(result["similarity"] * 100)
        content_preview = result["content"][:300].replace("\n", " ")
        context_parts.append(f"\n  [{i}] ({similarity_pct}% match) {content_preview}")
    
    return "\n".join(context_parts)


def verify_architecture(question: str) -> None:
    """
    Check architectural decisions against past context.
    Call this before modifying core systems.
    
    Example:
        verify_architecture("How should Willow route agent queries?")
    """
    context = check_context(question, threshold=0.2)
    
    if context:
        print(context)
        print()
        print("Review past context before proceeding.")
    else:
        print(f"[RAG CONTEXT] No strong matches for: {question}")
        print("Proceeding without historical context.")
    
    print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        verify_architecture(query)
    else:
        print("Usage: python context_check.py <question>")
