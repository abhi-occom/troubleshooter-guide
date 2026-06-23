import hashlib
import csv
import io
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from .config import Settings
from .database import Database
from .intents import (
    build_router_inventory_answer,
    build_structured_router_answer,
    is_router_inventory_question,
)
from .identifiers import detect_identifiers, profile_identifiers
from .llm import NOT_FOUND_ANSWER, AnswerProvider, ProviderUnavailable
from .pdf_service import PdfError, extract_pdf
from .vector_store import VectorStore


class RagServices:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        vector_store: VectorStore,
        provider: AnswerProvider,
    ):
        self.settings = settings
        self.database = database
        self.vector_store = vector_store
        self.provider = provider

    def _public_document(self, document: dict[str, Any]) -> dict[str, Any]:
        summarized = self.database.document_summary(document)
        return {key: value for key, value in summarized.items() if key != "stored_name"}

    async def upload_document(self, upload: UploadFile) -> dict[str, Any]:
        filename = Path(upload.filename or "").name
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=415, detail="Only PDF files are supported.")

        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        content = await upload.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"PDF exceeds the {self.settings.max_upload_mb} MB limit.",
            )
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")

        sha256 = hashlib.sha256(content).hexdigest()
        duplicate = self.database.find_document_by_hash(sha256)
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This PDF has already been uploaded.",
                    "document_id": duplicate["id"],
                },
            )

        stored_name = f"{uuid4()}.pdf"
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        target = self.settings.upload_dir / stored_name
        target.write_bytes(content)
        document = self.database.create_document(filename, stored_name, sha256)
        try:
            indexed = self._index_document(document, target)
            if indexed["status"] == "indexed":
                self.database.replace_document_identifiers(
                    indexed["id"], profile_identifiers(indexed["filename"], None)
                )
            if (
                indexed["status"] == "indexed"
                and self.settings.enrichment_enabled
            ):
                self.database.create_enrichment_job(indexed["id"])
                indexed = self.database.get_document(indexed["id"])
            return self._public_document(indexed)
        except Exception:
            if document["status"] == "processing":
                self.database.update_document(
                    document["id"], status="failed", error="Unexpected indexing error."
                )
            raise

    def _index_document(self, document: dict[str, Any], path: Path) -> dict[str, Any]:
        try:
            extracted = extract_pdf(
                path, self.settings.chunk_size, self.settings.chunk_overlap
            )
        except PdfError as exc:
            return self.database.update_document(
                document["id"], status="failed", error=str(exc)
            )

        if extracted.character_count < self.settings.min_extracted_characters:
            self.vector_store.delete_document(document["id"])
            return self.database.update_document(
                document["id"],
                status="requires_ocr",
                page_count=len(extracted.pages),
                chunk_count=0,
                error="Insufficient extractable text. OCR is required.",
            )

        try:
            count = self.vector_store.add_document(
                document["id"], document["filename"], extracted.chunks
            )
        except Exception as exc:
            return self.database.update_document(
                document["id"],
                status="failed",
                page_count=len(extracted.pages),
                chunk_count=0,
                error=f"Embedding or vector indexing failed: {type(exc).__name__}",
            )
        return self.database.update_document(
            document["id"],
            status="indexed",
            page_count=len(extracted.pages),
            chunk_count=count,
            error=None,
        )

    def list_documents(self, **filters: Any) -> dict[str, Any]:
        return self.database.search_documents(**filters)

    def reindex_document(self, document_id: str) -> dict[str, Any]:
        document = self.database.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")
        path = self.settings.upload_dir / document["stored_name"]
        if not path.exists():
            raise HTTPException(status_code=410, detail="The stored PDF is missing.")
        self.database.cancel_active_enrichment_jobs(document_id)
        self.database.invalidate_document_enrichment(document_id)
        document = self.database.update_document(
            document_id,
            status="processing",
            version=document["version"] + 1,
            chunk_count=0,
            error=None,
        )
        indexed = self._index_document(document, path)
        if indexed["status"] == "indexed" and self.settings.enrichment_enabled:
            self.database.create_enrichment_job(document_id)
            indexed = self.database.get_document(document_id)
        if indexed["status"] == "indexed":
            self.database.replace_document_identifiers(
                document_id,
                profile_identifiers(
                    indexed["filename"], self.database.get_profile(document_id)
                ),
            )
        return self._public_document(indexed)

    def delete_document(self, document_id: str) -> None:
        document = self.database.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")
        self.vector_store.delete_document(document_id)
        path = self.settings.upload_dir / document["stored_name"]
        if path.exists():
            path.unlink()
        self.database.delete_document(document_id)

    def get_knowledge(self, document_id: str) -> dict[str, Any]:
        try:
            return self.database.get_knowledge(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Document not found.") from exc

    def update_profile(
        self, document_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.database.get_document(document_id):
            raise HTTPException(status_code=404, detail="Document not found.")
        try:
            profile = self.database.update_profile(document_id, changes)
            document = self.database.get_document(document_id)
            self.database.replace_document_identifiers(
                document_id, profile_identifiers(document["filename"], profile)
            )
            return profile
        except KeyError as exc:
            raise HTTPException(
                status_code=409,
                detail="The router profile has not been generated yet.",
            ) from exc

    def enqueue_enrichment(self, document_id: str) -> dict[str, Any]:
        document = self.database.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")
        if document["status"] != "indexed":
            raise HTTPException(
                status_code=409, detail="Only indexed documents can be enriched."
            )
        return self.database.create_enrichment_job(document_id)

    def update_faq(
        self, document_id: str, faq_id: str, approved: bool, alias_active: bool
    ) -> dict[str, Any]:
        faq = self.database.get_faq(faq_id)
        if not faq or faq["document_id"] != document_id:
            raise HTTPException(status_code=404, detail="FAQ not found.")
        if alias_active and not approved:
            raise HTTPException(
                status_code=422, detail="An active alias must also be approved."
            )
        if alias_active:
            document = self.database.get_document(document_id)
            self.vector_store.add_faq_alias(
                faq_id,
                document_id,
                faq["question"],
                faq["source_chunk_id"],
                faq["source_page"],
                document["filename"],
            )
        else:
            self.vector_store.delete_faq_alias(faq_id)
        return self.database.update_faq(faq_id, approved, alias_active)

    def create_dataset(self, name: str, description: str | None) -> dict:
        return self.database.create_evaluation_dataset(name, description)

    def get_dataset(self, dataset_id: str) -> dict:
        dataset = self.database.get_evaluation_dataset(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        dataset["questions"] = self.database.list_evaluation_questions(dataset_id)
        return dataset

    def update_dataset(self, dataset_id: str, changes: dict) -> dict:
        self.get_dataset(dataset_id)
        return self.database.update_evaluation_dataset(dataset_id, changes)

    def delete_dataset(self, dataset_id: str) -> None:
        if not self.database.delete_evaluation_dataset(dataset_id):
            raise HTTPException(status_code=404, detail="Dataset not found.")

    def save_evaluation_question(
        self, dataset_id: str, values: dict, question_id: str | None = None
    ) -> dict:
        if not self.database.get_evaluation_dataset(dataset_id):
            raise HTTPException(status_code=404, detail="Dataset not found.")
        existing = (
            self.database.get_evaluation_question(question_id) if question_id else None
        )
        validated = {**(existing or {}), **values}
        if validated.get("supported") and not validated.get("expected_document_id"):
            raise HTTPException(
                status_code=422,
                detail="Supported questions require expected_document_id.",
            )
        if validated.get("expected_document_id") and not self.database.get_document(
            validated["expected_document_id"]
        ):
            raise HTTPException(status_code=422, detail="Expected document not found.")
        if (
            validated.get("expected_page_start")
            and validated.get("expected_page_end")
            and validated["expected_page_end"] < validated["expected_page_start"]
        ):
            raise HTTPException(status_code=422, detail="Invalid expected page range.")
        try:
            if question_id:
                return self.database.update_evaluation_question(question_id, values)
            return self.database.add_evaluation_question(dataset_id, values)
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=409, detail="Question already exists in this dataset."
                ) from exc
            raise

    def import_evaluation_csv(self, dataset_id: str, content: str) -> dict:
        rows = list(csv.DictReader(io.StringIO(content)))
        required = {"question", "supported", "expected_document_id"}
        if not rows or not required.issubset(rows[0]):
            raise HTTPException(status_code=422, detail="Invalid CSV columns.")
        prepared = []
        errors = []
        existing_questions = {
            item["question"].casefold()
            for item in self.database.list_evaluation_questions(dataset_id)
        }
        incoming_questions: set[str] = set()
        for number, row in enumerate(rows, start=2):
            try:
                supported_value = row["supported"].strip().casefold()
                if supported_value not in {"1", "0", "true", "false", "yes", "no"}:
                    raise ValueError("supported must be true or false")
                supported = supported_value in {"1", "true", "yes"}
                normalized_question = row["question"].strip().casefold()
                if not normalized_question:
                    raise ValueError("question is required")
                if (
                    normalized_question in existing_questions
                    or normalized_question in incoming_questions
                ):
                    raise ValueError("duplicate question")
                incoming_questions.add(normalized_question)
                values = {
                    "question": row["question"].strip(),
                    "supported": supported,
                    "expected_document_id": row["expected_document_id"].strip() or None,
                    "expected_page_start": int(row["expected_page_start"])
                    if row.get("expected_page_start", "").strip()
                    else None,
                    "expected_page_end": int(row["expected_page_end"])
                    if row.get("expected_page_end", "").strip()
                    else None,
                    "topic": row.get("topic") or None,
                    "reference_answer": row.get("reference_answer") or None,
                    "key_points": [
                        item.strip()
                        for item in row.get("required_key_points", "").split("|")
                        if item.strip()
                    ],
                    "notes": row.get("notes") or None,
                    "enabled": row.get("enabled", "true").strip().casefold()
                    not in {"0", "false", "no"},
                }
                if supported and not values["expected_document_id"]:
                    raise ValueError("supported question requires expected_document_id")
                if values["expected_document_id"] and not self.database.get_document(
                    values["expected_document_id"]
                ):
                    raise ValueError("expected document not found")
                prepared.append(values)
            except Exception as exc:
                errors.append({"row": number, "error": str(exc)})
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        created = [self.save_evaluation_question(dataset_id, row) for row in prepared]
        return {"imported": len(created)}

    def export_evaluation_csv(self, dataset_id: str) -> str:
        output = io.StringIO()
        fields = [
            "question", "supported", "expected_document_id", "expected_page_start",
            "expected_page_end", "topic", "reference_answer",
            "required_key_points", "notes", "enabled",
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in self.database.list_evaluation_questions(dataset_id):
            writer.writerow(
                {
                    **{key: item.get(key) for key in fields if key != "required_key_points"},
                    "required_key_points": "|".join(item["key_points"]),
                }
            )
        return output.getvalue()

    def create_evaluation_run(self, dataset_id: str) -> dict:
        self.get_dataset(dataset_id)
        versions = {
            item["id"]: item["version"] for item in self.database.list_documents()
        }
        config = {
            "retrieval_top_k": self.settings.retrieval_top_k,
            "max_distance": self.settings.max_distance,
            "provider": self.provider.name,
            "model": getattr(self.provider, "model", None),
        }
        return self.database.create_evaluation_run(dataset_id, config, versions)

    def create_session(self) -> dict[str, Any]:
        return self.database.create_session(self.settings.session_ttl_minutes)

    def retrieve(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        detected = detect_identifiers(query, self.database.list_identifiers())
        document_ids = sorted({item["document_id"] for item in detected})
        diagnostics = {
            "detected_identifiers": [item["display_value"] for item in detected],
            "matched_document_ids": document_ids,
            "mode": "global",
            "fallback_used": False,
        }
        if document_ids:
            strict = self.vector_store.query(
                query,
                self.settings.retrieval_top_k,
                self.settings.max_distance,
                document_ids=document_ids,
            )
            if strict:
                diagnostics["mode"] = "strict"
                diagnostics["candidate_distances"] = [
                    item["distance"] for item in strict
                ]
                return strict, diagnostics
            diagnostics["fallback_used"] = True
        matches = self.vector_store.query(
            query, self.settings.retrieval_top_k, self.settings.max_distance
        )
        diagnostics["candidate_distances"] = [item["distance"] for item in matches]
        return matches, diagnostics

    def _active_session(self, session_id: str) -> dict[str, Any]:
        session = self.database.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        if datetime.fromisoformat(session["expires_at"]) <= datetime.now(UTC):
            self.database.delete_session(session_id)
            raise HTTPException(status_code=410, detail="Chat session has expired.")
        return session

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        self._active_session(session_id)
        return self.database.get_messages(session_id)

    def delete_session(self, session_id: str) -> None:
        if not self.database.delete_session(session_id):
            raise HTTPException(status_code=404, detail="Chat session not found.")

    def ask(self, session_id: str, question: str) -> dict[str, Any]:
        request_id = str(uuid4())
        started = time.perf_counter()
        rewritten_query: str | None = None
        grounded = False
        citations: list[dict[str, Any]] = []
        error_code: str | None = None

        try:
            self._active_session(session_id)
            history = self.database.get_messages(
                session_id, limit=self.settings.memory_turns * 2
            )
            if is_router_inventory_question(question):
                answer = build_router_inventory_answer(
                    self.database.get_indexed_profiles()
                )
                self.database.add_message(session_id, "user", question)
                self.database.add_message(
                    session_id,
                    "assistant",
                    answer,
                    grounded=True,
                    citations=[],
                )
                self.database.touch_session(
                    session_id, self.settings.session_ttl_minutes
                )
                grounded = True
                return {
                    "request_id": request_id,
                    "session_id": session_id,
                    "answer": answer,
                    "grounded": True,
                    "retrieval_status": "grounded",
                    "rewritten_query": None,
                    "citations": [],
                    "retrieval_diagnostics": None,
                }
            structured_answer = build_structured_router_answer(
                question, self.database.get_indexed_profiles()
            )
            if structured_answer:
                self.database.add_message(session_id, "user", question)
                self.database.add_message(
                    session_id,
                    "assistant",
                    structured_answer,
                    grounded=True,
                    citations=[],
                )
                self.database.touch_session(
                    session_id, self.settings.session_ttl_minutes
                )
                grounded = True
                return {
                    "request_id": request_id,
                    "session_id": session_id,
                    "answer": structured_answer,
                    "grounded": True,
                    "retrieval_status": "grounded",
                    "rewritten_query": None,
                    "citations": [],
                    "retrieval_diagnostics": None,
                }

            rewritten_query = self.provider.rewrite_query(question, history)
            citations, diagnostics = self.retrieve(rewritten_query)
            self.database.add_message(session_id, "user", question)

            if not citations:
                answer = NOT_FOUND_ANSWER
            else:
                answer = self.provider.answer(
                    question, rewritten_query, history, citations
                )
                grounded = answer.strip() != NOT_FOUND_ANSWER
                if not grounded:
                    citations = []

            self.database.add_message(
                session_id,
                "assistant",
                answer,
                rewritten_query=(
                    rewritten_query if rewritten_query != question else None
                ),
                grounded=grounded,
                citations=citations,
            )
            self.database.touch_session(session_id, self.settings.session_ttl_minutes)
            return {
                "request_id": request_id,
                "session_id": session_id,
                "answer": answer,
                "grounded": grounded,
                "retrieval_status": "grounded" if grounded else "not_found",
                "rewritten_query": (
                    rewritten_query if rewritten_query != question else None
                ),
                "citations": citations,
                "retrieval_diagnostics": diagnostics,
            }
        except ProviderUnavailable as exc:
            error_code = "provider_unavailable"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        finally:
            self.database.add_question_log(
                request_id=request_id,
                session_id=session_id,
                question=question,
                rewritten_query=rewritten_query,
                grounded=grounded,
                citation_count=len(citations),
                latency_ms=int((time.perf_counter() - started) * 1000),
                error_code=error_code,
            )
