from pathlib import Path
from typing import Any

import fitz
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from app.main import create_app
from app.services import RagServices


class FakeVectorStore:
    def __init__(self):
        self.documents: dict[str, list[dict[str, Any]]] = {}
        self.query_results: list[dict[str, Any]] = []
        self.queries: list[str] = []
        self.aliases: dict[str, dict[str, Any]] = {}

    def add_document(self, document_id, filename, chunks):
        self.documents[document_id] = [
            {
                "id": f"{document_id}:{chunk.page}:{chunk.chunk_index}",
                "document_id": document_id,
                "document": filename,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "excerpt": chunk.text,
                "distance": 0.1,
            }
            for chunk in chunks
        ]
        return len(chunks)

    def delete_document(self, document_id):
        self.documents.pop(document_id, None)
        self.aliases = {
            faq_id: alias
            for faq_id, alias in self.aliases.items()
            if alias["document_id"] != document_id
        }

    def query(
        self,
        text,
        top_k,
        max_distance,
        *,
        include_aliases=True,
        document_ids=None,
    ):
        self.queries.append(text)
        results = self.query_results
        if document_ids:
            results = [
                item for item in results if item["document_id"] in document_ids
            ]
        return results[:top_k]

    def get_document_chunks(self, document_id):
        return self.documents.get(document_id, [])

    def add_faq_alias(
        self, faq_id, document_id, question, source_chunk_id, source_page, filename
    ):
        self.aliases[faq_id] = {
            "document_id": document_id,
            "question": question,
            "source_chunk_id": source_chunk_id,
        }

    def delete_faq_alias(self, faq_id):
        self.aliases.pop(faq_id, None)

    def healthcheck(self):
        return True


class FakeProvider:
    name = "ollama"

    def __init__(self):
        self.history_lengths: list[int] = []

    def rewrite_query(self, question, history):
        self.history_lengths.append(len(history))
        if history and "it" in question.lower():
            return "HOME MESH PRO red LED after reset"
        return question

    def answer(self, question, rewritten_query, history, sources):
        return "Restart the router, then wait for the status light to stabilize."

    def configured(self):
        return True

    def healthcheck(self):
        return True

    def extract_knowledge(self, chunks):
        first = chunks[0]
        return {
            "profile": {
                "router_name": "HOME MESH PRO",
                "model": "Wi-Fi 7",
                "product_id": "171118",
                "supported_configuration": "Two mesh units",
                "features": ["Wi-Fi 7"],
                "topics": ["reset"],
            },
            "provenance": {
                "router_name": {
                    "chunk_id": first["id"],
                    "page": first["page"],
                    "excerpt": first["text"][:100],
                }
            },
            "faqs": [
                {
                    "question": "How do I reset HOME MESH PRO?",
                    "expected_topic": "reset",
                    "source_chunk_id": first["id"],
                }
            ],
        }

    def judge_answer(self, question, answer, reference_answer, evidence):
        return {"score": 0.9, "explanation": "Grounded in expected evidence."}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        anthropic_api_key="test-key",
        min_extracted_characters=20,
        memory_turns=5,
        enrichment_enabled=False,
    )


@pytest.fixture
def services(settings: Settings):
    database = Database(settings.database_path)
    database.initialize()
    vector_store = FakeVectorStore()
    provider = FakeProvider()
    return RagServices(settings, database, vector_store, provider)


@pytest.fixture
def client(services: RagServices):
    app = create_app()
    app.state.services = services
    with TestClient(app) as test_client:
        yield test_client


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content
