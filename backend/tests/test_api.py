from io import BytesIO

from .conftest import make_pdf


def test_upload_list_reindex_and_delete(client, services):
    response = client.post(
        "/api/documents",
        files={
            "file": (
                "router.pdf",
                make_pdf(
                    "HOME MESH PRO router reset instructions. "
                    "Hold the reset button for ten seconds."
                ),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "indexed"
    assert document["page_count"] == 1
    assert document["chunk_count"] >= 1

    listed = client.get("/api/documents").json()
    assert [item["id"] for item in listed["items"]] == [document["id"]]

    reindexed = client.post(
        f"/api/documents/{document['id']}/reindex"
    ).json()
    assert reindexed["version"] == 2
    assert reindexed["status"] == "indexed"

    deleted = client.delete(f"/api/documents/{document['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/documents").json()["items"] == []
    assert document["id"] not in services.vector_store.documents


def test_duplicate_pdf_is_rejected(client):
    content = make_pdf(
        "A sufficiently long router manual describing reset and LED behavior."
    )
    files = {"file": ("same.pdf", content, "application/pdf")}
    assert client.post("/api/documents", files=files).status_code == 201
    duplicate = client.post(
        "/api/documents",
        files={"file": ("copy.pdf", content, "application/pdf")},
    )
    assert duplicate.status_code == 409
    assert "already been uploaded" in duplicate.json()["detail"]["message"]


def test_scanned_or_empty_text_pdf_requires_ocr(client):
    response = client.post(
        "/api/documents",
        files={"file": ("scan.pdf", make_pdf("x"), "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "requires_ocr"


def test_non_pdf_is_rejected(client):
    response = client.post(
        "/api/documents",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 415


def test_health_reports_components(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": True,
        "vector_store": True,
        "embedding_model": True,
        "llm_provider": "ollama",
        "llm_configured": True,
        "llm_available": True,
    }


def test_knowledge_profile_and_regenerate_endpoints(client, services):
    document = services.database.create_document(
        "router.pdf", "stored.pdf", "knowledge-hash"
    )
    services.database.update_document(document["id"], status="indexed")
    services.database.upsert_extracted_profile(
        document["id"],
        {
            "router_name": "Original Router",
            "model": "Model A",
            "product_id": None,
            "supported_configuration": None,
            "features": [],
            "topics": [],
        },
        {},
    )

    knowledge = client.get(
        f"/api/documents/{document['id']}/knowledge"
    )
    assert knowledge.status_code == 200
    assert knowledge.json()["profile"]["router_name"] == "Original Router"

    updated = client.patch(
        f"/api/documents/{document['id']}/profile",
        json={"router_name": "Corrected Router"},
    )
    assert updated.status_code == 200
    assert updated.json()["router_name"] == "Corrected Router"
    assert "router_name" in updated.json()["manual_fields"]

    queued = client.post(f"/api/documents/{document['id']}/enrich")
    assert queued.status_code == 202
    assert queued.json()["status"] == "queued"


def test_upload_enqueues_background_enrichment_without_waiting(client, services):
    services.settings.enrichment_enabled = True

    response = client.post(
        "/api/documents",
        files={
            "file": (
                "automatic-router.pdf",
                make_pdf(
                    "Automatic Router setup instructions and reset troubleshooting. "
                    "Hold the reset button for ten seconds."
                ),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "indexed"
    assert response.json()["enrichment_status"] == "queued"
    knowledge = client.get(
        f"/api/documents/{response.json()['id']}/knowledge"
    ).json()
    assert knowledge["job"]["status"] == "queued"
