from app.pdf_service import TextChunk
from app.vector_store import VectorStore


def test_faq_alias_resolves_to_authoritative_source_chunk(tmp_path):
    store = VectorStore(tmp_path / "chroma", "test_aliases")
    document_id = "doc-1"
    source_id = f"{document_id}:1:0"
    source_text = "Hold the reset button for ten seconds."
    store.add_document(
        document_id,
        "router.pdf",
        [TextChunk(source_text, page=1, chunk_index=0)],
    )
    store.add_faq_alias(
        "faq-1",
        document_id,
        "How do I factory reset the device?",
        source_id,
        1,
        "router.pdf",
    )

    matches = store.query(
        "How do I factory reset the device?",
        top_k=3,
        max_distance=1.0,
    )

    assert matches[0]["excerpt"] == source_text
    assert matches[0]["document"] == "router.pdf"
    assert matches[0]["page"] == 1


def test_query_can_be_restricted_to_exact_document_ids(tmp_path):
    store = VectorStore(tmp_path / "chroma-filter", "test_filters")
    store.add_document(
        "ax52",
        "RT-AX52.pdf",
        [TextChunk("Reset the RT-AX52 router.", page=1, chunk_index=0)],
    )
    store.add_document(
        "ax53",
        "RT-AX53.pdf",
        [TextChunk("Reset the RT-AX53 router.", page=1, chunk_index=0)],
    )

    matches = store.query(
        "How do I reset RT AX52?",
        top_k=3,
        max_distance=1.0,
        document_ids=["ax52"],
    )

    assert matches
    assert {item["document_id"] for item in matches} == {"ax52"}
