from app.identifiers import detect_identifiers, normalize_identifier


def test_identifier_normalization_accepts_spacing_and_hyphens():
    assert normalize_identifier("RT-AX52") == "rtax52"
    assert normalize_identifier("RT AX52") == "rtax52"
    assert normalize_identifier("rtax52") == "rtax52"


def test_identifier_detection_prefers_known_exact_normalized_value():
    known = [
        {
            "document_id": "doc-1",
            "display_value": "RT-AX52",
            "normalized_value": "rtax52",
        },
        {
            "document_id": "doc-2",
            "display_value": "RT-AX53",
            "normalized_value": "rtax53",
        },
    ]
    matches = detect_identifiers("How do I reset RT AX52?", known)
    assert [item["document_id"] for item in matches] == ["doc-1"]


def test_strict_retrieval_and_global_fallback(services):
    first = services.database.create_document("RT-AX52.pdf", "a.pdf", "id-hash-1")
    second = services.database.create_document("RT-AX53.pdf", "b.pdf", "id-hash-2")
    services.database.update_document(first["id"], status="indexed")
    services.database.update_document(second["id"], status="indexed")
    services.database.replace_document_identifiers(
        first["id"], [("model", "RT-AX52")]
    )
    services.database.replace_document_identifiers(
        second["id"], [("model", "RT-AX53")]
    )
    services.vector_store.query_results = [
        {
            "document_id": first["id"],
            "document": "RT-AX52.pdf",
            "page": 1,
            "excerpt": "Reset AX52.",
            "distance": 0.1,
        },
        {
            "document_id": second["id"],
            "document": "RT-AX53.pdf",
            "page": 1,
            "excerpt": "Reset AX53.",
            "distance": 0.05,
        },
    ]

    matches, diagnostics = services.retrieve("Reset RT AX52")
    assert [item["document_id"] for item in matches] == [first["id"]]
    assert diagnostics["mode"] == "strict"
    assert diagnostics["fallback_used"] is False

    services.vector_store.query_results = [
        {
            "document_id": second["id"],
            "document": "RT-AX53.pdf",
            "page": 1,
            "excerpt": "General fallback.",
            "distance": 0.2,
        }
    ]
    matches, diagnostics = services.retrieve("Reset RT AX52")
    assert matches[0]["document_id"] == second["id"]
    assert diagnostics["fallback_used"] is True
