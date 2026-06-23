from app.database import Database
from app.enrichment import EnrichmentService
from app.pdf_service import TextChunk


def prepare_document(services):
    document = services.database.create_document(
        "home-mesh-pro.pdf", "stored.pdf", "enrichment-hash"
    )
    services.database.update_document(document["id"], status="indexed")
    services.vector_store.add_document(
        document["id"],
        document["filename"],
        [
            TextChunk(
                text=(
                    "HOME MESH PRO Wi-Fi 7 router. Product ID 171118. "
                    "Hold reset for ten seconds."
                ),
                page=1,
                chunk_index=0,
            )
        ],
    )
    services.vector_store.query_results = [
        {
            "source_chunk_id": f"{document['id']}:1:0",
            "document_id": document["id"],
            "document": document["filename"],
            "page": 1,
            "excerpt": "Hold reset for ten seconds.",
            "distance": 0.1,
        }
    ]
    return services.database.get_document(document["id"])


def test_enrichment_job_extracts_profile_faq_and_evaluation(services):
    document = prepare_document(services)
    job = services.database.create_enrichment_job(document["id"])
    enrichment = EnrichmentService(
        services.database,
        services.vector_store,
        services.provider,
        batch_characters=12000,
        top_k=5,
        max_distance=0.65,
    )

    assert enrichment.run_once() is True

    knowledge = services.database.get_knowledge(document["id"])
    assert knowledge["job"]["status"] == "completed"
    assert knowledge["profile"]["router_name"] == "HOME MESH PRO"
    assert knowledge["profile"]["provenance"]["router_name"]["page"] == 1
    assert len(knowledge["faqs"]) == 1
    assert knowledge["faqs"][0]["passed"] is True
    assert knowledge["faqs"][0]["approved"] is True
    assert knowledge["faqs"][0]["alias_active"] is True
    assert knowledge["faqs"][0]["id"] in services.vector_store.aliases


def test_manual_profile_fields_survive_regeneration(services):
    document = prepare_document(services)
    services.database.upsert_extracted_profile(
        document["id"],
        {
            "router_name": "Extracted Name",
            "model": "Wi-Fi 7",
            "product_id": None,
            "supported_configuration": None,
            "features": [],
            "topics": [],
        },
        {},
    )
    services.database.update_profile(
        document["id"], {"router_name": "Corrected Router Name"}
    )

    services.database.upsert_extracted_profile(
        document["id"],
        {
            "router_name": "New Extracted Name",
            "model": "Wi-Fi 7 Plus",
            "product_id": "123",
            "supported_configuration": "Two units",
            "features": ["Mesh"],
            "topics": ["reset"],
        },
        {},
    )

    profile = services.database.get_profile(document["id"])
    assert profile["router_name"] == "Corrected Router Name"
    assert profile["model"] == "Wi-Fi 7 Plus"
    assert profile["extracted_values"]["router_name"] == "New Extracted Name"
    assert profile["manual_fields"] == ["router_name"]


def test_running_jobs_are_requeued_after_database_restart(settings):
    database = Database(settings.database_path)
    database.initialize()
    document = database.create_document("router.pdf", "stored.pdf", "restart-hash")
    database.update_document(document["id"], status="indexed")
    job = database.create_enrichment_job(document["id"])
    claimed = database.claim_next_enrichment_job()
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "running"

    restarted = Database(settings.database_path)
    restarted.initialize()

    recovered = restarted.get_enrichment_job(job["id"])
    assert recovered["status"] == "queued"
    assert recovered["error"] == "Recovered after restart"


def test_job_claim_is_exclusive(services):
    document = prepare_document(services)
    services.database.create_enrichment_job(document["id"])

    first = services.database.claim_next_enrichment_job()
    second = services.database.claim_next_enrichment_job()

    assert first is not None
    assert second is None


def test_deleting_document_cascades_generated_knowledge(services):
    document = prepare_document(services)
    services.database.upsert_extracted_profile(
        document["id"],
        {
            "router_name": "Router",
            "model": None,
            "product_id": None,
            "supported_configuration": None,
            "features": [],
            "topics": [],
        },
        {},
    )
    services.database.create_enrichment_job(document["id"])

    services.delete_document(document["id"])

    assert services.database.get_profile(document["id"]) is None
    assert services.database.get_document(document["id"]) is None
    assert services.vector_store.aliases == {}
