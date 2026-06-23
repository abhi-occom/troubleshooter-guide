import httpx
import pytest

from app.llm import NOT_FOUND_ANSWER, OllamaProvider, ProviderUnavailable


def make_provider(handler) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://localhost:11434",
        model="llama3.2:3b",
        transport=httpx.MockTransport(handler),
    )


def test_ollama_healthcheck_requires_configured_model():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "llama3.2:3b"}]},
        )

    assert make_provider(handler).healthcheck() is True


def test_ollama_rewrites_follow_up_with_chat_api():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = __import__("json").loads(request.content)
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["model"] == "llama3.2:3b"
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "HOME MESH PRO red LED after reset",
                }
            },
        )

    provider = make_provider(handler)
    result = provider.rewrite_query(
        "What if it stays red?",
        [{"role": "user", "content": "How do I reset HOME MESH PRO?"}],
    )

    assert result == "HOME MESH PRO red LED after reset"


def test_ollama_disables_thinking_for_grounded_answers():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert payload["think"] is False
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "Ten seconds.",
                },
                "done_reason": "stop",
            },
        )

    result = make_provider(handler).answer(
        "How long should I hold reset?",
        "router reset duration",
        [],
        [{"document": "router.pdf", "page": 1, "excerpt": "Hold reset for ten seconds."}],
    )

    assert result == "Ten seconds."


def test_ollama_empty_content_reports_model_and_done_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "Reasoning consumed the token budget.",
                },
                "done_reason": "length",
            },
        )

    with pytest.raises(
        ProviderUnavailable,
        match="llama3.2:3b.*done reason: length",
    ):
        make_provider(handler).answer(
            "Question",
            "Question",
            [],
            [{"document": "router.pdf", "page": 1, "excerpt": "Text"}],
        )


def test_ollama_generates_grounded_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "Hold the reset button for ten seconds.",
                }
            },
        )

    provider = make_provider(handler)
    result = provider.answer(
        "How do I reset it?",
        "How to reset HOME MESH PRO",
        [],
        [
            {
                "document": "router.pdf",
                "page": 4,
                "excerpt": "Hold the reset button for ten seconds.",
            }
        ],
    )

    assert result == "Hold the reset button for ten seconds."


def test_ollama_connection_error_becomes_user_facing_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = make_provider(handler)

    with pytest.raises(ProviderUnavailable, match="Cannot connect to Ollama"):
        provider.answer(
            "Question",
            "Question",
            [],
            [{"document": "router.pdf", "page": 1, "excerpt": "Text"}],
        )


def test_ollama_extracts_structured_knowledge():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert payload["think"] is False
        assert payload["format"]["type"] == "object"
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": __import__("json").dumps(
                        {
                            "profile": {
                                "router_name": "HOME MESH PRO",
                                "model": "Wi-Fi 7",
                                "product_id": None,
                                "supported_configuration": "Two units",
                                "features": ["Mesh"],
                                "topics": ["reset"],
                            },
                            "provenance": {},
                            "faqs": [],
                        }
                    )
                }
            },
        )

    result = make_provider(handler).extract_knowledge(
        [{"id": "doc:1:0", "page": 1, "text": "HOME MESH PRO"}]
    )
    assert result["profile"]["router_name"] == "HOME MESH PRO"


@pytest.mark.parametrize("content", ["", "not-json", "```json\n[]\n```"])
def test_ollama_rejects_invalid_enrichment_json(content):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": content}})

    with pytest.raises(ProviderUnavailable):
        make_provider(handler).extract_knowledge(
            [{"id": "doc:1:0", "page": 1, "text": "Router text"}]
        )


def test_ollama_accepts_partial_enrichment_object_for_merge_layer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": '{"profile":{"router_name":"Router X"}}'}},
        )

    result = make_provider(handler).extract_knowledge(
        [{"id": "doc:1:0", "page": 1, "text": "Router X"}]
    )
    assert result == {"profile": {"router_name": "Router X"}}


def test_ollama_enrichment_timeout_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderUnavailable, match="enrichment timed out"):
        make_provider(handler).extract_knowledge(
            [{"id": "doc:1:0", "page": 1, "text": "Router text"}]
        )
