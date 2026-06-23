import json
import re
from typing import Any, Protocol

import httpx
from anthropic import Anthropic


NOT_FOUND_ANSWER = "I could not find this in the uploaded router guide."


class ProviderUnavailable(Exception):
    pass


class AnswerProvider(Protocol):
    name: str

    def rewrite_query(self, question: str, history: list[dict]) -> str: ...

    def answer(
        self, question: str, rewritten_query: str, history: list[dict], sources: list[dict]
    ) -> str: ...

    def configured(self) -> bool: ...

    def healthcheck(self) -> bool: ...

    def extract_knowledge(self, chunks: list[dict[str, Any]]) -> dict[str, Any]: ...

    def judge_answer(
        self, question: str, answer: str, reference_answer: str, evidence: str
    ) -> dict[str, Any] | None: ...


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = Anthropic(api_key=api_key) if api_key else None

    def _require_client(self) -> Anthropic:
        if self.client is None:
            raise ProviderUnavailable("ANTHROPIC_API_KEY is not configured.")
        return self.client

    def configured(self) -> bool:
        return self.client is not None

    def healthcheck(self) -> bool:
        return self.configured()

    def extract_knowledge(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        raise ProviderUnavailable(
            "Automatic enrichment currently requires the Ollama provider."
        )

    def judge_answer(
        self, question: str, answer: str, reference_answer: str, evidence: str
    ) -> dict[str, Any] | None:
        return None

    def rewrite_query(self, question: str, history: list[dict]) -> str:
        if not history:
            return question
        transcript = "\n".join(
            f"{item['role']}: {item['content']}" for item in history[-10:]
        )
        response = self._require_client().messages.create(
            model=self.model,
            max_tokens=180,
            temperature=0,
            system=(
                "Rewrite the latest router-support question as one standalone search "
                "query. Resolve pronouns and omitted model names from the conversation. "
                "Do not answer the question or add facts. Return only the query."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Conversation:\n{transcript}\n\nLatest question:\n{question}",
                }
            ],
        )
        rewritten = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        return rewritten or question

    def answer(
        self, question: str, rewritten_query: str, history: list[dict], sources: list[dict]
    ) -> str:
        source_text = "\n\n".join(
            f"[Source {index}: {source['document']}, page {source['page']}]\n"
            f"{source['excerpt']}"
            for index, source in enumerate(sources, start=1)
        )
        history_text = "\n".join(
            f"{item['role']}: {item['content']}" for item in history[-10:]
        )
        response = self._require_client().messages.create(
            model=self.model,
            max_tokens=700,
            temperature=0,
            system=(
                "You are the Occom Router Support Assistant. Answer only from the "
                "provided manual excerpts. Conversation history can clarify the user's "
                "meaning but is never evidence. If the excerpts do not support an answer, "
                f"respond exactly: {NOT_FOUND_ANSWER} Keep the answer concise, practical, "
                "and preserve warnings and step order. Do not invent citations."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Recent conversation (context only):\n{history_text or '(none)'}\n\n"
                        f"Original question:\n{question}\n\n"
                        f"Standalone retrieval query:\n{rewritten_query}\n\n"
                        f"Manual excerpts:\n{source_text}"
                    ),
                }
            ],
        )
        answer = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        return answer or NOT_FOUND_ANSWER


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[:-4]
        self.model = model.strip()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def _chat(self, system: str, user: str, max_tokens: int) -> str:
        if not self.configured():
            raise ProviderUnavailable(
                "OLLAMA_BASE_URL and OLLAMA_MODEL must be configured."
            )
        try:
            response = self.client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "options": {
                        "temperature": 0,
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("message", {}).get("content", "").strip()
            if not content:
                done_reason = payload.get("done_reason", "unknown")
                raise ProviderUnavailable(
                    f"Ollama model '{self.model}' returned no final answer "
                    f"(done reason: {done_reason})."
                )
            return content
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Start Ollama and confirm OLLAMA_BASE_URL."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(
                f"Ollama timed out while running model '{self.model}'."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise ProviderUnavailable(
                f"Ollama request failed ({exc.response.status_code}): {detail}"
            ) from exc
        except (ValueError, KeyError) as exc:
            raise ProviderUnavailable("Ollama returned an invalid response.") from exc

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ProviderUnavailable(
                    "Ollama returned malformed enrichment JSON."
                ) from exc
            try:
                value = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as nested:
                raise ProviderUnavailable(
                    "Ollama returned malformed enrichment JSON."
                ) from nested
        if not isinstance(value, dict):
            raise ProviderUnavailable("Ollama enrichment response must be a JSON object.")
        return value

    def extract_knowledge(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        if not chunks:
            raise ProviderUnavailable("No PDF chunks are available for enrichment.")
        context = "\n\n".join(
            f"[chunk_id={chunk['id']} page={chunk['page']}]\n{chunk['text']}"
            for chunk in chunks
        )
        schema = {
            "type": "object",
            "properties": {
                "profile": {
                    "type": "object",
                    "properties": {
                        "router_name": {"type": ["string", "null"]},
                        "model": {"type": ["string", "null"]},
                        "product_id": {"type": ["string", "null"]},
                        "supported_configuration": {"type": ["string", "null"]},
                        "features": {"type": "array", "items": {"type": "string"}},
                        "topics": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "router_name",
                        "model",
                        "product_id",
                        "supported_configuration",
                        "features",
                        "topics",
                    ],
                },
                "provenance": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "chunk_id": {"type": "string"},
                            "page": {"type": "integer"},
                            "excerpt": {"type": "string"},
                        },
                        "required": ["chunk_id", "page", "excerpt"],
                    },
                },
                "faqs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "expected_topic": {"type": "string"},
                            "source_chunk_id": {"type": "string"},
                        },
                        "required": [
                            "question",
                            "expected_topic",
                            "source_chunk_id",
                        ],
                    },
                },
            },
            "required": ["profile", "provenance", "faqs"],
        }
        try:
            response = self.client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "format": schema,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Extract router knowledge only from the supplied PDF "
                                "chunks. Never guess. Use null or empty arrays when a "
                                "field is unsupported. Generate 3 to 8 practical FAQ "
                                "questions. Every provenance and FAQ source_chunk_id must "
                                "exactly match a supplied chunk_id. Return JSON only."
                            ),
                        },
                        {"role": "user", "content": context},
                    ],
                    "options": {"temperature": 0, "num_predict": 1800},
                },
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            if not content.strip():
                raise ProviderUnavailable("Ollama returned empty enrichment JSON.")
            return self._parse_json(content)
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(
                f"Cannot connect to Ollama at {self.base_url}."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("Ollama enrichment timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(
                f"Ollama enrichment failed ({exc.response.status_code})."
            ) from exc

    def judge_answer(
        self, question: str, answer: str, reference_answer: str, evidence: str
    ) -> dict[str, Any] | None:
        content = self._chat(
            system=(
                "Grade the candidate answer against the reference and evidence. "
                "Return JSON only: {\"score\": number from 0 to 1, "
                "\"explanation\": \"short reason\"}."
            ),
            user=(
                f"Question: {question}\nReference: {reference_answer}\n"
                f"Evidence: {evidence}\nCandidate: {answer}"
            ),
            max_tokens=180,
        )
        value = self._parse_json(content)
        return {
            "score": max(0.0, min(1.0, float(value.get("score", 0)))),
            "explanation": str(value.get("explanation", ""))[:500],
        }

    def healthcheck(self) -> bool:
        if not self.configured():
            return False
        try:
            response = self.client.get("/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            available = {
                item.get("name") or item.get("model")
                for item in models
                if isinstance(item, dict)
            }
            return self.model in available
        except (httpx.HTTPError, ValueError):
            return False

    def rewrite_query(self, question: str, history: list[dict]) -> str:
        if not history:
            return question
        transcript = "\n".join(
            f"{item['role']}: {item['content']}" for item in history[-10:]
        )
        return self._chat(
            system=(
                "Rewrite the latest router-support question as one standalone search "
                "query. Resolve pronouns and omitted model names from the conversation. "
                "Do not answer the question or add facts. Return only the query."
            ),
            user=f"Conversation:\n{transcript}\n\nLatest question:\n{question}",
            max_tokens=180,
        )

    def answer(
        self, question: str, rewritten_query: str, history: list[dict], sources: list[dict]
    ) -> str:
        source_text = "\n\n".join(
            f"[Source {index}: {source['document']}, page {source['page']}]\n"
            f"{source['excerpt']}"
            for index, source in enumerate(sources, start=1)
        )
        history_text = "\n".join(
            f"{item['role']}: {item['content']}" for item in history[-10:]
        )
        return self._chat(
            system=(
                "You are the Occom Router Support Assistant. Answer only from the "
                "provided manual excerpts. Conversation history can clarify the user's "
                "meaning but is never evidence. If the excerpts do not support an answer, "
                f"respond exactly: {NOT_FOUND_ANSWER} Keep the answer concise, practical, "
                "and preserve warnings and step order. Do not invent citations."
            ),
            user=(
                f"Recent conversation (context only):\n{history_text or '(none)'}\n\n"
                f"Original question:\n{question}\n\n"
                f"Standalone retrieval query:\n{rewritten_query}\n\n"
                f"Manual excerpts:\n{source_text}"
            ),
            max_tokens=700,
        )


def create_provider(
    provider_name: str,
    *,
    anthropic_api_key: str,
    claude_model: str,
    ollama_base_url: str,
    ollama_model: str,
    ollama_api_key: str,
    ollama_timeout_seconds: float,
) -> AnswerProvider:
    if provider_name == "claude":
        return ClaudeProvider(anthropic_api_key, claude_model)
    if provider_name == "ollama":
        return OllamaProvider(
            base_url=ollama_base_url,
            model=ollama_model,
            api_key=ollama_api_key,
            timeout_seconds=ollama_timeout_seconds,
        )
    raise ValueError(f"Unsupported LLM provider: {provider_name}")
