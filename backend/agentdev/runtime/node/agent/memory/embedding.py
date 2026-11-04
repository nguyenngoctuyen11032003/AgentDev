"""Optional, keyless embedding providers for memory stores.

Embedding is optional: memory stores without one use keyword (BM25) retrieval
(see ``keyword_search``). The only provider is ``local`` (sentence-transformers),
which runs on this machine without any API key.
"""

from abc import ABC, abstractmethod
import re
import logging
from typing import List

from agentdev.entity.configs import EmbeddingConfig

logger = logging.getLogger(__name__)

_warned_providers: set[str] = set()


class EmbeddingBase(ABC):
    def __init__(self, embedding_config: EmbeddingConfig):
        self.config = embedding_config

    @abstractmethod
    def get_embedding(self, text):
        ...

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text to improve embedding quality."""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove special characters and emoji
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)
        
        # Clean up whitespace again
        text = re.sub(r'\s+', ' ', text.strip())
        
        return text

    def _chunk_text(self, text: str, max_length: int = 500) -> List[str]:
        """Split long text into chunks to improve embedding quality."""
        if len(text) <= max_length:
            return [text]
        
        # Split by sentence boundaries
        sentences = re.split(r'[\u3002\uff01\uff1f\uff1b\n]', text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            if len(current_chunk + sentence) <= max_length:
                current_chunk += sentence + "\u3002"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + "\u3002"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

class EmbeddingFactory:
    @staticmethod
    def create_embedding(embedding_config: EmbeddingConfig | None) -> "EmbeddingBase | None":
        """Build the configured embedding, or ``None`` to use keyword retrieval."""
        if embedding_config is None:
            return None
        provider = (embedding_config.provider or "").strip().lower()
        if provider == "local":
            return LocalEmbedding(embedding_config)
        if provider not in _warned_providers:
            _warned_providers.add(provider)
            logger.warning(
                "Embedding provider '%s' is not supported (only the 'local' model is); "
                "using keyword retrieval instead.",
                provider or "<unset>",
            )
        return None


class LocalEmbedding(EmbeddingBase):
    def __init__(self, embedding_config: EmbeddingConfig):
        super().__init__(embedding_config)
        params = embedding_config.params or {}
        self.model_path = params.get('model_path') or embedding_config.model
        self.device = params.get('device', 'cpu')
        self._fallback_dim = 768  # Default; updated after first successful call
        
        if not self.model_path:
            raise ValueError("LocalEmbedding requires a model (or params.model_path)")
        
        # Load the local embedding model (e.g., sentence-transformers)
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_path, device=self.device)
        except ImportError:
            raise ImportError("sentence-transformers is required for LocalEmbedding")

    def get_embedding(self, text):
        # Preprocess text before encoding
        processed_text = self._preprocess_text(text)
        
        if not processed_text:
            return [0.0] * self._fallback_dim
        
        try:
            embedding = self.model.encode(processed_text, convert_to_tensor=False)
            result = embedding.tolist()
            self._fallback_dim = len(result)
            return result
        except Exception as e:
            logger.error(f"Error getting local embedding: {e}")
            return [0.0] * self._fallback_dim
