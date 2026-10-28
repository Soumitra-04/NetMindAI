"""Minimal client for a locally running Ollama instance."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


class OllamaClient:
    def __init__(
        self,
        model: str = "qwen3:4b",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat_json(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        num_predict: int = 150,
    ) -> dict[str, Any]:
        """Request a JSON response from the local model."""
        format_schema = schema or {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["scenario_id", "rationale"],
            "additionalProperties": False,
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": format_schema,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,
            },
        }

        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(
                f"Ollama returned HTTP {exc.code}."
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                "Cannot connect to Ollama at "
                f"{self.base_url}. Is Ollama running?"
            ) from exc
        except TimeoutError as exc:
            raise RuntimeError("Ollama request timed out.") from exc

        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response.")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Ollama did not return valid JSON."
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError("Ollama response must be a JSON object.")

        return parsed
