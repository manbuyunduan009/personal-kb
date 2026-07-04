import hashlib
import math
import re
from typing import List


class EmbeddingProvider:
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class FastEmbedEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "fastembed is not installed. Run: pip install -r requirements.txt"
                ) from exc
            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return [vector.tolist() for vector in self.model.embed(texts)]


class HashEmbeddingProvider(EmbeddingProvider):
    """Dependency-free lexical embedding for first-run plumbing checks."""

    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token, weight in lexical_tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little", signed=False)
            index = value % self.dimensions
            vector[index] += weight

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def lexical_tokens(text: str) -> List[tuple[str, float]]:
    compact = re.sub(r"\s+", "", text.lower())
    tokens = []
    weights = {1: 0.25, 2: 1.0, 3: 1.4}
    for size, weight in weights.items():
        if len(compact) >= size:
            tokens.extend(
                (compact[index : index + size], weight)
                for index in range(len(compact) - size + 1)
            )
    return tokens


def create_embedding_provider(provider: str, model_name: str) -> EmbeddingProvider:
    normalized = provider.strip().lower()
    if normalized == "fastembed":
        return FastEmbedEmbeddingProvider(model_name)
    if normalized == "hash":
        return HashEmbeddingProvider()
    raise RuntimeError("Unsupported EMBEDDING_PROVIDER: %s" % provider)
