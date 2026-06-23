import threading
from collections import OrderedDict
from typing import Any
from uuid import uuid4

from .database import Database
from .llm import AnswerProvider, ProviderUnavailable
from .identifiers import profile_identifiers
from .vector_store import VectorStore


PROFILE_FIELDS = (
    "router_name",
    "model",
    "product_id",
    "supported_configuration",
)


class EnrichmentService:
    def __init__(
        self,
        database: Database,
        vector_store: VectorStore,
        provider: AnswerProvider,
        *,
        batch_characters: int,
        top_k: int,
        max_distance: float,
    ):
        self.database = database
        self.vector_store = vector_store
        self.provider = provider
        self.batch_characters = batch_characters
        self.top_k = top_k
        self.max_distance = max_distance

    def _batches(self, chunks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        batches: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        size = 0
        for chunk in chunks:
            chunk_size = len(chunk["text"])
            if current and size + chunk_size > self.batch_characters:
                batches.append(current)
                current = []
                size = 0
            current.append(chunk)
            size += chunk_size
        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _merge(results: list[dict[str, Any]]) -> dict[str, Any]:
        profile: dict[str, Any] = {
            "router_name": None,
            "model": None,
            "product_id": None,
            "supported_configuration": None,
            "features": [],
            "topics": [],
        }
        provenance: dict[str, Any] = {}
        faq_by_question: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for result in results:
            extracted = result.get("profile") or {}
            for field in PROFILE_FIELDS:
                if not profile[field] and extracted.get(field):
                    profile[field] = str(extracted[field]).strip()
            for field in ("features", "topics"):
                values = [
                    str(item).strip()
                    for item in extracted.get(field, [])
                    if str(item).strip()
                ]
                profile[field] = list(dict.fromkeys([*profile[field], *values]))
            provenance.update(result.get("provenance") or {})
            for faq in result.get("faqs") or []:
                question = str(faq.get("question", "")).strip()
                if question:
                    faq_by_question.setdefault(question.casefold(), faq)
        return {
            "profile": profile,
            "provenance": provenance,
            "faqs": list(faq_by_question.values()),
        }

    def process_job(self, job: dict[str, Any]) -> None:
        document_id = job["document_id"]
        document = self.database.get_document(document_id)
        if not document or document["status"] != "indexed":
            raise ProviderUnavailable("Document is not available for enrichment.")
        chunks = self.vector_store.get_document_chunks(document_id)
        if not chunks:
            raise ProviderUnavailable("Indexed document contains no source chunks.")
        chunk_by_id = {chunk["id"]: chunk for chunk in chunks}
        batches = self._batches(chunks)
        results = []
        for index, batch in enumerate(batches, start=1):
            results.append(self.provider.extract_knowledge(batch))
            current_job = self.database.get_enrichment_job(job["id"])
            if not current_job or current_job["status"] != "running":
                return
            progress = 10 + int((index / len(batches)) * 45)
            self.database.update_enrichment_job(job["id"], progress=progress)

        merged = self._merge(results)
        valid_provenance = {}
        for field, source in merged["provenance"].items():
            if not isinstance(source, dict):
                continue
            chunk = chunk_by_id.get(source.get("chunk_id"))
            if chunk:
                valid_provenance[field] = {
                    "chunk_id": chunk["id"],
                    "page": chunk["page"],
                    "excerpt": str(source.get("excerpt") or chunk["text"][:300]),
                }
        profile = self.database.upsert_extracted_profile(
            document_id, merged["profile"], valid_provenance
        )
        self.database.replace_document_identifiers(
            document_id, profile_identifiers(document["filename"], profile)
        )
        self.database.update_enrichment_job(job["id"], progress=65)

        existing_faqs = self.database.list_faqs(document_id)
        for existing in existing_faqs:
            self.vector_store.delete_faq_alias(existing["id"])

        faqs = []
        for raw in merged["faqs"]:
            chunk = chunk_by_id.get(raw.get("source_chunk_id"))
            question = str(raw.get("question", "")).strip()
            if not chunk or not question:
                continue
            faqs.append(
                {
                    "id": str(uuid4()),
                    "question": question,
                    "expected_topic": str(raw.get("expected_topic") or "").strip(),
                    "source_chunk_id": chunk["id"],
                    "source_page": chunk["page"],
                    "source_excerpt": chunk["text"][:600],
                }
            )
        self.database.replace_faqs(document_id, faqs)
        self.database.update_enrichment_job(job["id"], progress=75)

        for index, faq in enumerate(self.database.list_faqs(document_id), start=1):
            matches = self.vector_store.query(
                faq["question"],
                self.top_k,
                self.max_distance,
                include_aliases=False,
            )
            expected_found = any(
                match["document_id"] == document_id
                and match.get("source_chunk_id") == faq["source_chunk_id"]
                for match in matches
            )
            best_distance = min(
                (match["distance"] for match in matches), default=None
            )
            passed = bool(matches and expected_found)
            self.database.save_faq_evaluation(
                faq["id"],
                passed=passed,
                best_distance=best_distance,
                retrieved_pages=sorted({match["page"] for match in matches}),
                expected_source_found=expected_found,
            )
            if passed:
                self.database.update_faq(faq["id"], approved=True, alias_active=True)
                self.vector_store.add_faq_alias(
                    faq["id"],
                    document_id,
                    faq["question"],
                    faq["source_chunk_id"],
                    faq["source_page"],
                    document["filename"],
                )
            progress = 75 + int((index / max(len(faqs), 1)) * 20)
            self.database.update_enrichment_job(job["id"], progress=progress)
        self.database.update_enrichment_job(
            job["id"], status="completed", progress=100, error=None
        )

    def run_once(self) -> bool:
        job = self.database.claim_next_enrichment_job()
        if not job:
            return False
        try:
            self.process_job(job)
        except Exception as exc:
            self.database.retry_or_fail_enrichment_job(
                job["id"], f"{type(exc).__name__}: {str(exc)[:500]}"
            )
        return True


class EnrichmentWorker:
    def __init__(self, service: EnrichmentService, poll_seconds: float):
        self.service = service
        self.poll_seconds = poll_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run, name="router-enrichment-worker", daemon=True
        )
        self.thread.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            worked = self.service.run_once()
            if not worked:
                self.stop_event.wait(self.poll_seconds)

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
