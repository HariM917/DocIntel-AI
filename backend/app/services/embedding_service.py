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

    def chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 80) -> List[Dict[str, Any]]:
        """Splits document text into overlapping chunks suitable for semantic search and RAG."""
        if not text:
            return []

        paragraphs = text.split("\n\n")
        chunks: List[Dict[str, Any]] = []
        current_chunk = ""
        chunk_idx = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append({
                        "chunk_id": chunk_idx,
                        "text": current_chunk,
                    })
                    chunk_idx += 1
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
                                chunks.append({
                                    "chunk_id": chunk_idx,
                                    "text": sub_chunk,
                                })
                                chunk_idx += 1
                            sub_chunk = s
                    if sub_chunk:
                        current_chunk = sub_chunk

        if current_chunk:
            chunks.append({
                "chunk_id": chunk_idx,
                "text": current_chunk,
            })

        return chunks

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
