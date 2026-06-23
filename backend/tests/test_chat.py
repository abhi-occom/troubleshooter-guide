from app.llm import NOT_FOUND_ANSWER


def test_grounded_answer_is_saved_with_citation(client, services):
    session = client.post("/api/chat/sessions").json()
    services.vector_store.query_results = [
        {
            "document_id": "doc-1",
            "document": "router.pdf",
            "page": 4,
            "excerpt": "Hold reset for ten seconds.",
            "distance": 0.12,
        }
    ]

    response = client.post(
        "/api/ask",
        json={"session_id": session["id"], "question": "How do I reset it?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["citations"][0]["page"] == 4

    messages = client.get(
        f"/api/chat/sessions/{session['id']}/messages"
    ).json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["citations"][0]["document"] == "router.pdf"


def test_follow_up_is_rewritten_and_freshly_retrieved(client, services):
    session = client.post("/api/chat/sessions").json()
    services.vector_store.query_results = [
        {
            "document_id": "doc-1",
            "document": "router.pdf",
            "page": 2,
            "excerpt": "Reset instructions.",
            "distance": 0.1,
        }
    ]
    client.post(
        "/api/ask",
        json={
            "session_id": session["id"],
            "question": "How do I reset HOME MESH PRO?",
        },
    )
    response = client.post(
        "/api/ask",
        json={"session_id": session["id"], "question": "What if it stays red?"},
    )

    assert response.status_code == 200
    assert response.json()["rewritten_query"] == "HOME MESH PRO red LED after reset"
    assert services.vector_store.queries[-1] == "HOME MESH PRO red LED after reset"
    assert len(services.vector_store.queries) == 2
    assert services.provider.history_lengths[-1] == 2


def test_no_retrieval_match_returns_fixed_not_found(client, services):
    session = client.post("/api/chat/sessions").json()
    services.vector_store.query_results = []

    response = client.post(
        "/api/ask",
        json={"session_id": session["id"], "question": "Can it make coffee?"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == NOT_FOUND_ANSWER
    assert response.json()["citations"] == []
    assert response.json()["grounded"] is False


def test_deleting_session_removes_conversation(client):
    session = client.post("/api/chat/sessions").json()
    assert client.delete(f"/api/chat/sessions/{session['id']}").status_code == 204
    response = client.get(f"/api/chat/sessions/{session['id']}/messages")
    assert response.status_code == 404


def test_router_inventory_question_counts_indexed_guides_without_llm(
    client, services
):
    first = services.database.create_document(
        "home-mesh-pro-setup.pdf", "first.pdf", "hash-1"
    )
    second = services.database.create_document(
        "Business_Router_X1_manual.pdf", "second.pdf", "hash-2"
    )
    ignored = services.database.create_document(
        "scanned-router.pdf", "third.pdf", "hash-3"
    )
    services.database.update_document(first["id"], status="indexed")
    services.database.update_document(second["id"], status="indexed")
    services.database.update_document(ignored["id"], status="requires_ocr")
    session = client.post("/api/chat/sessions").json()

    response = client.post(
        "/api/ask",
        json={
            "session_id": session["id"],
            "question": "How many routers can we configure?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["citations"] == []
    assert "2 router setup guides are currently available" in body["answer"]
    assert "Home Mesh Pro" in body["answer"]
    assert "Business Router X1" in body["answer"]
    assert "Which router are you asking about?" in body["answer"]
    assert services.provider.history_lengths == []
    assert services.vector_store.queries == []


def test_router_inventory_answer_handles_no_indexed_guides(client):
    session = client.post("/api/chat/sessions").json()

    response = client.post(
        "/api/ask",
        json={"session_id": session["id"], "question": "List the routers"},
    )

    assert response.status_code == 200
    assert "no indexed router setup guides" in response.json()["answer"].lower()
