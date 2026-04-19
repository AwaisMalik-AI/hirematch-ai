"""OpenAI-compatible chat + embeddings via HTTP (no SDK secrets in code paths)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _fallback_embedding(text: str, dimensions: int = 256) -> list[float]:
    """Deterministic bag-of-chars vector for offline / no-key environments (not true semantics)."""
    text = (text or "").lower()
    vec = [0.0] * dimensions
    for i, ch in enumerate(text):
        idx = ord(ch) % dimensions
        vec[idx] += 1.0 + 1.0 / (1 + i)
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self._settings.llm_api_key)

    def _headers(self) -> dict[str, str]:
        key = self._settings.llm_api_key
        if not key:
            return {}
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM_API_KEY is not configured")

        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._settings.llm_model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            r = await client.post(url, headers=self._headers(), json=payload)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    def chat_json_sync(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM_API_KEY is not configured")

        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._settings.llm_model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        with httpx.Client(timeout=self._settings.llm_timeout_seconds) as client:
            r = client.post(url, headers=self._headers(), json=payload)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.enabled:
            dim = min(256, self._settings.embedding_dimensions)
            return [_fallback_embedding(t, dim) for t in texts]

        url = f"{self._settings.llm_base_url.rstrip('/')}/embeddings"
        payload = {"model": self._settings.embedding_model, "input": texts}
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            r = await client.post(url, headers=self._headers(), json=payload)
            r.raise_for_status()
            data = r.json()
        out = sorted(data["data"], key=lambda x: x["index"])
        return [row["embedding"] for row in out]

    def embed_texts_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.enabled:
            dim = min(256, self._settings.embedding_dimensions)
            return [_fallback_embedding(t, dim) for t in texts]

        url = f"{self._settings.llm_base_url.rstrip('/')}/embeddings"
        payload = {"model": self._settings.embedding_model, "input": texts}
        with httpx.Client(timeout=self._settings.llm_timeout_seconds) as client:
            r = client.post(url, headers=self._headers(), json=payload)
            r.raise_for_status()
            data = r.json()
        out = sorted(data["data"], key=lambda x: x["index"])
        return [row["embedding"] for row in out]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


_SKILL_ALIASES: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "k8s": "kubernetes",
    "tf": "tensorflow",
    "k8": "kubernetes",
    "node": "nodejs",
    "node.js": "nodejs",
    "react.js": "react",
    "vue.js": "vue",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "aws": "amazon web services",
    "gcp": "google cloud",
    "azure cloud": "azure",
    "c#": "csharp",
    ".net": "dotnet",
    "go lang": "go",
    "golang": "go",
}


def normalize_skill_token(raw: str) -> str:
    s = raw.strip().lower()
    s = re.sub(r"[^a-z0-9+#.\s-]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return _SKILL_ALIASES.get(s, s)


def normalize_skills(skills: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in skills:
        n = normalize_skill_token(x)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def stable_id(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return h
