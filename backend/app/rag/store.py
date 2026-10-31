from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "how", "i", "if", "in", "is", "it", "me", "my", "of", "on", "or",
    "our", "please", "the", "to", "was", "we", "what", "when", "where", "which",
    "who", "why", "will", "with", "you", "your",
}


@dataclass(slots=True)
class FAQChunk:
    id: str
    question: str
    answer: str
    tags: list[str]
    source: str

    @property
    def searchable_text(self) -> str:
        return f"{self.question} {' '.join(self.tags)} {self.answer}"


def _tokens(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS]


class FAQStore:
    """FAQ retrieval with a semantic backend and a dependency-free lexical fallback."""

    def __init__(
        self,
        path: Path | None = None,
        backend: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        self.path = path or settings.resolve_path(settings.faq_path)
        self.requested_backend = (backend or settings.rag_backend).lower()
        self.embedding_model_name = embedding_model or settings.embedding_model
        self.chunks: list[FAQChunk] = []
        self.backend = "lexical"
        self._idf: dict[str, float] = {}
        self._lexical_vectors: list[dict[str, float]] = []
        self._embedding_model = None
        self._faiss_index = None
        self._matrix = None
        self._load()
        self._build()

    def _load(self) -> None:
        if not self.path.exists():
            logger.warning("FAQ file not found: %s", self.path)
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    self.chunks.append(
                        FAQChunk(
                            id=str(item.get("id") or f"faq-{line_no}"),
                            question=str(item.get("question") or ""),
                            answer=str(item.get("answer") or ""),
                            tags=[str(tag) for tag in item.get("tags") or []],
                            source=str(item.get("source") or "faq"),
                        )
                    )
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("Skipping malformed FAQ line %d: %s", line_no, exc)
        logger.info("Loaded %d FAQ chunks from %s", len(self.chunks), self.path)

    def _try_semantic(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                self.embedding_model_name,
                local_files_only=settings.embedding_local_only,
            )
            texts = [chunk.searchable_text for chunk in self.chunks]
            embeddings = model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
            self._embedding_model = model
            try:
                import faiss
                import numpy as np

                matrix = np.asarray(embeddings, dtype="float32")
                index = faiss.IndexFlatIP(matrix.shape[1])
                index.add(matrix)
                self._faiss_index = index
            except Exception:
                self._matrix = embeddings
            self.backend = "semantic"
            logger.info(
                "FAQ retrieval using sentence-transformers (%s) with %d chunks",
                self.embedding_model_name,
                len(self.chunks),
            )
            return True
        except Exception as exc:
            logger.info("Semantic FAQ backend unavailable (%s); using lexical search", exc)
            return False

    def _build(self) -> None:
        if not self.chunks:
            return
        if self.requested_backend in {"auto", "semantic"} and self._try_semantic():
            return
        if self.requested_backend == "semantic":
            logger.warning("RAG_BACKEND=semantic requested but unavailable; falling back to lexical")
        self.backend = "lexical"
        documents = [_tokens(chunk.searchable_text) for chunk in self.chunks]
        document_count = len(documents)
        frequency: dict[str, int] = {}
        for document in documents:
            for token in set(document):
                frequency[token] = frequency.get(token, 0) + 1
        self._idf = {
            token: math.log((1 + document_count) / (1 + count)) + 1.0
            for token, count in frequency.items()
        }
        for document in documents:
            counts: dict[str, int] = {}
            for token in document:
                counts[token] = counts.get(token, 0) + 1
            vector = {
                token: (1 + math.log(count)) * self._idf.get(token, 1.0)
                for token, count in counts.items()
            }
            norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
            self._lexical_vectors.append({key: value / norm for key, value in vector.items()})
        logger.info("FAQ retrieval using lexical TF-IDF with %d chunks", len(self.chunks))

    def _semantic_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        if self._embedding_model is None:
            return []
        query_vector = self._embedding_model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        if self._faiss_index is not None:
            scores, indices = self._faiss_index.search(
                query_vector.reshape(1, -1).astype("float32"), top_k
            )
            return [(int(index), float(score)) for score, index in zip(scores[0], indices[0], strict=False) if index >= 0]
        import numpy as np

        scores = np.asarray(self._matrix) @ np.asarray(query_vector)
        order = scores.argsort()[::-1][:top_k]
        return [(int(index), float(scores[index])) for index in order]

    def _lexical_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        counts: dict[str, int] = {}
        for token in _tokens(query):
            counts[token] = counts.get(token, 0) + 1
        if not counts:
            return []
        vector = {
            token: (1 + math.log(count)) * self._idf.get(token, 1.0)
            for token, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vector = {key: value / norm for key, value in vector.items()}
        scored = []
        for index, document in enumerate(self._lexical_vectors):
            score = sum(value * document.get(token, 0.0) for token, value in vector.items())
            if score > 0:
                scored.append((index, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        if not query.strip() or not self.chunks:
            return []
        limit = top_k or settings.rag_top_k
        results = (
            self._semantic_search(query, limit)
            if self.backend == "semantic"
            else self._lexical_search(query, limit)
        )
        threshold = (
            settings.rag_min_semantic_score
            if self.backend == "semantic"
            else settings.rag_min_score
        )
        matches = []
        for index, score in results:
            if score < threshold:
                continue
            chunk = self.chunks[index]
            matches.append(
                {
                    "id": chunk.id,
                    "question": chunk.question,
                    "answer": chunk.answer,
                    "tags": chunk.tags,
                    "source": chunk.source,
                    "score": round(float(score), 4),
                    "backend": self.backend,
                }
            )
        return matches


@lru_cache
def get_faq_store() -> FAQStore:
    return FAQStore()
