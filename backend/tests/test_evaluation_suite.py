from app.evaluation import EvaluationService


def test_document_search_pagination_and_filters(services):
    for index in range(105):
        document = services.database.create_document(
            f"Router-{index:03}.pdf", f"{index}.pdf", f"search-hash-{index}"
        )
        services.database.update_document(
            document["id"],
            status="indexed" if index % 2 == 0 else "failed",
        )
    page = services.database.search_documents(
        search="Router", status="indexed", page=2, page_size=25
    )
    assert page["total"] == 53
    assert page["page"] == 2
    assert len(page["items"]) == 25
    assert page["total_pages"] == 3


def test_csv_import_export_and_persistent_evaluation_run(services):
    document = services.database.create_document(
        "RT-AX52.pdf", "router.pdf", "eval-hash"
    )
    services.database.update_document(document["id"], status="indexed", version=3)
    services.database.replace_document_identifiers(
        document["id"], [("model", "RT-AX52")]
    )
    services.vector_store.query_results = [
        {
            "document_id": document["id"],
            "document": "RT-AX52.pdf",
            "page": 4,
            "excerpt": "Hold reset for ten seconds.",
            "distance": 0.1,
        }
    ]
    dataset = services.create_dataset("Real support", "Pilot questions")
    csv_text = (
        "question,supported,expected_document_id,expected_page_start,"
        "expected_page_end,topic,reference_answer,required_key_points,notes,enabled\n"
        f"How do I reset RT-AX52?,true,{document['id']},4,4,reset,"
        "Restart the router and wait.,restart|status light,,true\n"
    )
    imported = services.import_evaluation_csv(dataset["id"], csv_text)
    assert imported == {"imported": 1}
    assert "required_key_points" in services.export_evaluation_csv(dataset["id"])

    run = services.create_evaluation_run(dataset["id"])
    evaluator = EvaluationService(services)
    claimed = services.database.claim_evaluation_run()
    assert claimed["id"] == run["id"]
    evaluator.process_run(claimed)

    completed = services.database.get_evaluation_run(run["id"])
    results = services.database.list_evaluation_results(run["id"])
    assert completed["status"] == "completed"
    assert completed["passed"] is True
    assert completed["document_versions"][document["id"]] == 3
    assert completed["metrics"]["top3_accuracy"] == 1.0
    assert results[0]["key_point_score"] == 1.0
    assert results[0]["judge_score"] == 0.9


def test_invalid_csv_does_not_partially_import(services):
    dataset = services.create_dataset("Invalid import", None)
    content = (
        "question,supported,expected_document_id\n"
        "Missing document,true,does-not-exist\n"
    )
    try:
        services.import_evaluation_csv(dataset["id"], content)
    except Exception:
        pass
    assert services.database.list_evaluation_questions(dataset["id"]) == []
