"""DeepSeek V3 client — OpenAI-compatible API + local fastembed for vectors."""

from __future__ import annotations

import os
from typing import Optional
from openai import AsyncOpenAI
from fastembed import TextEmbedding

_client: Optional[AsyncOpenAI] = None
_embedder: Optional[TextEmbedding] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        import httpx
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise EnvironmentError("DEEPSEEK_API_KEY not set. Copy .env.example to .env and fill in your key.")
        # Disable proxy auto-detection to avoid macOS SOCKS proxy issues
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            http_client=httpx.AsyncClient(trust_env=False),
        )
    return _client


def _get_embedder() -> TextEmbedding:
    """Lazy-init fastembed (ONNX, no PyTorch required)."""
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedder


async def chat(
    prompt: str,
    system: str = "You are a villager in a small medieval village. Stay in character.",
    temperature: float = 0.8,
    max_tokens: int = 400,
) -> str:
    """Single-turn chat completion via DeepSeek V3."""
    client = _get_client()
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def embed(text: str) -> list[float]:
    """Local embedding via fastembed (BAAI/bge-small-en-v1.5, 384-dim)."""
    embedder = _get_embedder()
    vectors = list(embedder.embed([text]))
    return vectors[0].tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embed for efficiency."""
    embedder = _get_embedder()
    return [v.tolist() for v in embedder.embed(texts)]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """1 - cosine_similarity. 0 = identical, 2 = opposite."""
    import numpy as np
    va, vb = np.array(a), np.array(b)
    dot = float(np.dot(va, vb))
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if norm == 0:
        return 1.0
    return 1.0 - dot / norm
