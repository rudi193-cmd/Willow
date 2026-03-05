"""
Local Embeddings — sentence-transformers wrapper for Willow.

Model: all-MiniLM-L6-v2 (~80MB, 384-dim vectors, CPU-friendly)
Falls back gracefully if not installed.

pip install sentence-transformers

GOVERNANCE: Runs 100% local. No data leaves the machine.
CHECKSUM: DS=42
"""

import logging
import struct
import math

_model = None
_available = None  # None = not checked yet


def _load():
    """Lazy-load the embedding model. Called once."""
    global _model, _available
    if _available is not None:
        return
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        _available = True
        logging.info("EMBEDDINGS: all-MiniLM-L6-v2 loaded (384-dim, CPU)")
    except ImportError:
        _available = False
        logging.debug("EMBEDDINGS: sentence-transformers not installed — pip install sentence-transformers")
    except Exception as e:
        _available = False
        logging.warning(f"EMBEDDINGS: Failed to load model: {e}")


def is_available() -> bool:
    """Check if embedding model is loaded. Triggers lazy load."""
    _load()
    return _available


def embed(text: str) -> bytes:
    """
    Encode text to 384-dim float32 vector, returned as bytes for SQLite BLOB storage.
    Returns None if model not available.
    """
    _load()
    if not _available or not text:
        return None
    try:
        vec = _model.encode(text, show_progress_bar=False)
        return struct.pack(f'{len(vec)}f', *vec)
    except Exception as e:
        logging.debug(f"EMBEDDINGS: encode failed: {e}")
        return None


def cosine_similarity(a: bytes, b: bytes) -> float:
    """Compute cosine similarity between two packed vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dim = len(a) // 4
    va = struct.unpack(f'{dim}f', a)
    vb = struct.unpack(f'{dim}f', b)
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(x * x for x in vb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
