from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Database
from .enrichment import EnrichmentService, EnrichmentWorker
from .evaluation import EvaluationService, EvaluationWorker
from .identifiers import profile_identifiers
from .llm import create_provider
from .schemas import (
    AskRequest,
    AskResponse,
    DocumentResponse,
    DocumentPageResponse,
    HealthResponse,
    FaqResponse,
    FaqUpdate,
    KnowledgeResponse,
    MessageResponse,
    ProfileResponse,
    ProfileUpdate,
    EnrichmentJobResponse,
    DatasetCreate,
    EvaluationQuestionInput,
    EvaluationRunResponse,
    SessionResponse,
)
from .services import RagServices
from .vector_store import VectorStore


def build_services() -> tuple[RagServices, EnrichmentWorker | None, EvaluationWorker]:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    database = Database(settings.database_path)
    database.initialize()
    vector_store = VectorStore(settings.chroma_dir, settings.chroma_collection)
    provider = create_provider(
        settings.llm_provider,
        anthropic_api_key=settings.anthropic_api_key,
        claude_model=settings.claude_model,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_api_key=settings.ollama_api_key,
        ollama_timeout_seconds=settings.ollama_timeout_seconds,
    )
    services = RagServices(settings, database, vector_store, provider)
    for document in database.list_documents():
        if document["status"] == "indexed":
            database.replace_document_identifiers(
                document["id"],
                profile_identifiers(
                    document["filename"], database.get_profile(document["id"])
                ),
            )
    worker = None
    if settings.enrichment_enabled:
        enrichment = EnrichmentService(
            database,
            vector_store,
            provider,
            batch_characters=settings.enrichment_batch_characters,
            top_k=settings.retrieval_top_k,
            max_distance=settings.max_distance,
        )
        worker = EnrichmentWorker(enrichment, settings.enrichment_poll_seconds)
    return services, worker, EvaluationWorker(EvaluationService(services))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "services"):
        (
            app.state.services,
            app.state.enrichment_worker,
            app.state.evaluation_worker,
        ) = build_services()
    worker = getattr(app.state, "enrichment_worker", None)
    evaluation_worker = getattr(app.state, "evaluation_worker", None)
    if worker:
        worker.start()
    if evaluation_worker:
        evaluation_worker.start()
    try:
        yield
    finally:
        if worker:
            worker.stop()
        if evaluation_worker:
            evaluation_worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Router Troubleshooting RAG",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post(
        "/api/documents",
        response_model=DocumentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_document(file: UploadFile = File(...)):
        return await app.state.services.upload_document(file)

    @app.get("/api/documents", response_model=DocumentPageResponse)
    def list_documents(
        search: str = "",
        document_status: str | None = None,
        enrichment_status: str | None = None,
        feature: str | None = None,
        topic: str | None = None,
        sort: str = "created_at",
        direction: str = "desc",
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ):
        return app.state.services.list_documents(
            search=search,
            status=document_status,
            enrichment_status=enrichment_status,
            feature=feature,
            topic=topic,
            sort=sort,
            direction=direction,
            page=page,
            page_size=page_size,
        )

    @app.post("/api/documents/{document_id}/reindex", response_model=DocumentResponse)
    def reindex_document(document_id: str):
        return app.state.services.reindex_document(document_id)

    @app.get(
        "/api/documents/{document_id}/knowledge",
        response_model=KnowledgeResponse,
    )
    def get_document_knowledge(document_id: str):
        return app.state.services.get_knowledge(document_id)

    @app.patch(
        "/api/documents/{document_id}/profile",
        response_model=ProfileResponse,
    )
    def update_document_profile(document_id: str, payload: ProfileUpdate):
        return app.state.services.update_profile(
            document_id, payload.model_dump(exclude_unset=True)
        )

    @app.post(
        "/api/documents/{document_id}/enrich",
        response_model=EnrichmentJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def enrich_document(document_id: str):
        return app.state.services.enqueue_enrichment(document_id)

    @app.patch(
        "/api/documents/{document_id}/faqs/{faq_id}",
        response_model=FaqResponse,
    )
    def update_document_faq(document_id: str, faq_id: str, payload: FaqUpdate):
        return app.state.services.update_faq(
            document_id, faq_id, payload.approved, payload.alias_active
        )

    @app.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_document(document_id: str):
        app.state.services.delete_document(document_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/chat/sessions",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_session():
        return app.state.services.create_session()

    @app.get(
        "/api/chat/sessions/{session_id}/messages",
        response_model=list[MessageResponse],
    )
    def get_messages(session_id: str):
        return app.state.services.get_messages(session_id)

    @app.delete(
        "/api/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    def delete_session(session_id: str):
        app.state.services.delete_session(session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/ask", response_model=AskResponse)
    def ask(payload: AskRequest):
        return app.state.services.ask(payload.session_id, payload.question.strip())

    @app.get("/api/health", response_model=HealthResponse)
    def health():
        services = app.state.services
        database = services.database.healthcheck()
        vectors = services.vector_store.healthcheck()
        configured = services.provider.configured()
        available = services.provider.healthcheck()
        return {
            "status": (
                "ok" if database and vectors and configured and available else "degraded"
            ),
            "database": database,
            "vector_store": vectors,
            "embedding_model": vectors,
            "llm_provider": services.provider.name,
            "llm_configured": configured,
            "llm_available": available,
        }

    @app.get("/api/evaluation/datasets")
    def list_datasets():
        return app.state.services.database.list_evaluation_datasets()

    @app.post("/api/evaluation/datasets", status_code=status.HTTP_201_CREATED)
    def create_dataset(payload: DatasetCreate):
        return app.state.services.create_dataset(payload.name, payload.description)

    @app.get("/api/evaluation/datasets/{dataset_id}")
    def get_dataset(dataset_id: str):
        return app.state.services.get_dataset(dataset_id)

    @app.patch("/api/evaluation/datasets/{dataset_id}")
    def update_dataset(dataset_id: str, payload: dict):
        return app.state.services.update_dataset(dataset_id, payload)

    @app.delete(
        "/api/evaluation/datasets/{dataset_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_dataset(dataset_id: str):
        app.state.services.delete_dataset(dataset_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/evaluation/datasets/{dataset_id}/questions",
        status_code=status.HTTP_201_CREATED,
    )
    def add_evaluation_question(dataset_id: str, payload: EvaluationQuestionInput):
        return app.state.services.save_evaluation_question(
            dataset_id, payload.model_dump()
        )

    @app.patch("/api/evaluation/questions/{question_id}")
    def update_evaluation_question(question_id: str, payload: dict):
        existing = app.state.services.database.get_evaluation_question(question_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Question not found.")
        return app.state.services.save_evaluation_question(
            existing["dataset_id"], payload, question_id
        )

    @app.delete(
        "/api/evaluation/questions/{question_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_evaluation_question(question_id: str):
        if not app.state.services.database.delete_evaluation_question(question_id):
            raise HTTPException(status_code=404, detail="Question not found.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/evaluation/datasets/{dataset_id}/import")
    async def import_evaluation_questions(
        dataset_id: str, file: UploadFile = File(...)
    ):
        return app.state.services.import_evaluation_csv(
            dataset_id, (await file.read()).decode("utf-8-sig")
        )

    @app.get("/api/evaluation/datasets/{dataset_id}/export")
    def export_evaluation_questions(dataset_id: str):
        content = app.state.services.export_evaluation_csv(dataset_id)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="evaluation-{dataset_id}.csv"'
            },
        )

    @app.post(
        "/api/evaluation/datasets/{dataset_id}/runs",
        response_model=EvaluationRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_evaluation_run(dataset_id: str):
        return app.state.services.create_evaluation_run(dataset_id)

    @app.get("/api/evaluation/runs/{run_id}", response_model=EvaluationRunResponse)
    def get_evaluation_run(run_id: str):
        run = app.state.services.database.get_evaluation_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")
        return run

    @app.get("/api/evaluation/runs/{run_id}/results")
    def get_evaluation_results(run_id: str):
        if not app.state.services.database.get_evaluation_run(run_id):
            raise HTTPException(status_code=404, detail="Run not found.")
        return app.state.services.database.list_evaluation_results(run_id)

    return app


app = create_app()
