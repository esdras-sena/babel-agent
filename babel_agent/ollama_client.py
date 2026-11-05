"""Talk to a local Ollama server. Never installs or pulls models."""

from __future__ import annotations

from typing import Any

from babel_agent.config import OLLAMA_BASE


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns an error."""


def _httpx():
    try:
        import httpx
    except ImportError as exc:
        raise OllamaError(
            "Missing dependency httpx. Install requirements: pip install -r requirements.txt"
        ) from exc
    return httpx


def _client(timeout: float = 120.0):
    httpx = _httpx()
    return httpx.Client(base_url=OLLAMA_BASE, timeout=timeout)


def is_reachable() -> bool:
    try:
        with _client(timeout=3.0) as client:
            r = client.get("/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def list_models() -> list[str]:
    """Return installed model names from GET /api/tags.

    Returns an empty list if Ollama is down or has no models.
    Does not pull or install anything.
    """
    try:
        with _client(timeout=5.0) as client:
            r = client.get("/api/tags")
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        raise OllamaError(
            "Cannot reach Ollama at "
            f"{OLLAMA_BASE}. Install Ollama (https://ollama.com), start it, "
            "then pull a model yourself, e.g. `ollama pull llama3.2`."
        ) from exc

    models = data.get("models") or []
    names: list[str] = []
    for m in models:
        name = m.get("name") or m.get("model")
        if name:
            names.append(name)
    return sorted(set(names))


def chat(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    format_json: bool = False,
    think: bool | None = False,
) -> str:
    """POST /api/chat (non-streaming) and return the assistant message content.

    By default sends think=False so thinking models (e.g. Qwen3) return spoken
    reply text in message.content instead of filling only message.thinking.
    Pass think=True to allow chain-of-thought, or think=None to omit the field.
    """
    if not model:
        raise OllamaError("No Ollama model selected. Choose one in the UI.")

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if think is not None:
        payload["think"] = think
    if format_json:
        payload["format"] = "json"

    try:
        with _client(timeout=180.0) as client:
            r = client.post("/api/chat", json=payload)
            if r.status_code >= 400:
                detail = r.text[:500]
                raise OllamaError(f"Ollama chat failed ({r.status_code}): {detail}")
            data = r.json()
    except OllamaError:
        raise
    except Exception as exc:
        raise OllamaError(
            f"Ollama request failed: {exc}. Is the server running at {OLLAMA_BASE}?"
        ) from exc

    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    if not content:
        # Thinking models may still put text only in thinking if think wasn't honored.
        thinking = (msg.get("thinking") or msg.get("reasoning") or "").strip()
        if thinking:
            content = thinking
    if not content:
        raise OllamaError(
            "Ollama returned an empty response. "
            "Thinking models (e.g. Qwen3) can leave message.content empty while "
            "filling message.thinking — this client sends think=false by default; "
            "if you still see this, check the model and Ollama version."
        )
    return content


def status_message() -> tuple[bool, list[str], str]:
    """Return (ok, models, human message) for the UI."""
    if not is_reachable():
        return (
            False,
            [],
            f"Ollama is not reachable at {OLLAMA_BASE}. "
            "Install it from https://ollama.com, start the service, "
            "then run e.g. `ollama pull llama3.2` and refresh models.",
        )
    try:
        models = list_models()
    except OllamaError as exc:
        return False, [], str(exc)
    if not models:
        return (
            False,
            [],
            "Ollama is running but has no models. "
            "Pull one yourself (we never install models for you), e.g. "
            "`ollama pull llama3.2`, then click Refresh models.",
        )
    return True, models, f"Found {len(models)} local model(s)."
