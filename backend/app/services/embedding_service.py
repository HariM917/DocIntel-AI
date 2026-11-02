import logging
import numpy as np
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger("docintel.embedding")


class EmbeddingService:
    """Generates dense vector embeddings using SentenceTransformers for RAG chunk retrieval."""

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self.model = None
        self._initialized = False
        self._dimension = 384  # Default dimension for all-MiniLM-L6-v2

    def _load_model(self):
        if self._initialized:
            return
        try:
            logger.info(f"Loading SentenceTransformer embedding model ({self.model_name})...")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            self._dimension = self.model.get_sentence_embedding_dimension()
            self._initialized = True
            logger.info(f"Embedding model '{self.model_name}' loaded. Dimension: {self._dimension}")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer model ({e}). Using deterministic dense vectorizer fallback.")
            self.model = None
            self._initialized = True
            self._dimension = 384

    @property
    def dimension(self) -> int:
        if not self._initialized:
            self._load_model()
        return self._dimension

    @property
    def model_version(self) -> str:
        """Generation tag for the current embedding model (Step 20)."""
        return settings.EMBEDDING_MODEL_VERSION

    @staticmethod
    def _is_heading(paragraph: str) -> bool:
        """Heuristic: a short single line that is all-caps or title-case."""
        if "\n" in paragraph or len(paragraph) > 80:
            return False
        if paragraph.startswith("---") or paragraph.endswith((".", ":", ";", ",")):
            return False
        if ":" in paragraph:
            return False
        return paragraph.isupper() or paragraph.istitle()

    def chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 80) -> List[Dict[str, Any]]:
        """Splits document text into overlapping semantic chunks (Step 19).

        Prefers paragraph/section boundaries over blind character splitting.
        Each chunk records the ``section`` it belongs to (when known), keeps the
        document's meaning intact, and noise (page-break markers) and tiny
        meaningless chunks are dropped.
        """
        if not text:
            return []

        min_chars = max(1, int(getattr(settings, "MIN_CHUNK_CHARS", 20)))
        paragraphs = text.split("\n\n")
        raw_chunks: List[Dict[str, Any]] = []
        current_chunk = ""
        current_section = ""
        chunk_idx = 0

        def _emit(chunk_text_value: str) -> None:
            nonlocal chunk_idx
            if chunk_text_value and chunk_text_value.strip():
                raw_chunks.append({
                    "chunk_id": chunk_idx,
                    "text": chunk_text_value,
                    "section": current_section or None,
                })
                chunk_idx += 1

        for para in paragraphs:
            para = para.strip()
            if not para or para == "--- Page Break ---":
                continue

            # A heading labels the following content; it is not emitted on its own.
            if self._is_heading(para):
                current_section = para
                continue

            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    _emit(current_chunk)
                    # Keep overlap from tail of current_chunk
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
                    current_chunk = overlap_text + ("\n\n" if overlap_text else "") + para
                else:
                    # Single paragraph exceeds chunk_size; subdivide by sentences
                    sentences = para.split(". ")
                    sub_chunk = ""
                    for s in sentences:
                        if len(sub_chunk) + len(s) <= chunk_size:
                            sub_chunk += (". " if sub_chunk else "") + s
                        else:
                            if sub_chunk:
                                _emit(sub_chunk)
                            sub_chunk = s
                    if sub_chunk:
                        current_chunk = sub_chunk

        if current_chunk:
            _emit(current_chunk)

        # Drop tiny/empty chunks and re-number deterministically.
        meaningful = [c for c in raw_chunks if len(c["text"].strip()) >= min_chars]
        for new_id, chunk in enumerate(meaningful):
            chunk["chunk_id"] = new_id
        return meaningful

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Embeds a list of strings into a normalized 2D numpy array of shape (N, dimension)."""
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        self._load_model()

        if self.model is not None:
            try:
                embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
                return embeddings.astype(np.float32)
            except Exception as e:
                logger.error(f"SentenceTransformer encoding error: {e}")

        # Deterministic hashing-based fallback embedding
        return self._deterministic_fallback_embeddings(texts)

    def embed_query(self, query: str) -> np.ndarray:
        """Embeds a single query string into a 1D numpy array."""
        arr = self.embed_texts([query])
        return arr[0] if len(arr) > 0 else np.zeros(self.dimension, dtype=np.float32)

    def _deterministic_fallback_embeddings(self, texts: List[str]) -> np.ndarray:
        """Fallback deterministic token frequency projection into unit hypersphere."""
        vectors = []
        for text in texts:
            vec = np.zeros(self._dimension, dtype=np.float32)
            words = text.lower().split()
            for w in words:
                # Hash word to dimension index
                idx = hash(w) % self._dimension
                vec[idx] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)


embedding_service = EmbeddingService()
