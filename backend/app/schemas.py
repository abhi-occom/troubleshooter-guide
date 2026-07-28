from typing import Literal

from pydantic import BaseModel, Field


DocumentStatus = Literal["processing", "indexed", "requires_ocr", "failed"]


class DocumentResponse(BaseModel):
    id: str
    filename: str
    sha256: str
    version: int
    status: DocumentStatus
    page_count: int
    chunk_count: int
    error: str | None
    enrichment_status: str
    enrichment_error: str | None
    profile_status: str
    faq_count: int
    evaluation_pass_count: int
    created_at: str
    updated_at: str


class ProfileResponse(BaseModel):
    document_id: str
    router_name: str | None = None
    model: str | None = None
    product_id: str | None = None
    supported_configuration: str | None = None
    features: list[str] = []
    topics: list[str] = []
    identifier_aliases: list[str] = []
    provenance: dict = {}
    extracted_values: dict = {}
    manual_fields: list[str] = []
    status: str
    created_at: str
    updated_at: str


class ProfileUpdate(BaseModel):
    router_name: str | None = None
    model: str | None = None
    product_id: str | None = None
    supported_configuration: str | None = None
    features: list[str] | None = None
    topics: list[str] | None = None
    identifier_aliases: list[str] | None = None


class FaqResponse(BaseModel):
    id: str
    document_id: str
    question: str
    expected_topic: str | None
    source_chunk_id: str
    source_page: int
    source_excerpt: str
    approved: bool
    alias_active: bool
    passed: bool | None = None
    best_distance: float | None = None
    retrieved_pages: list[int] = []
    expected_source_found: bool | None = None
    evaluated_at: str | None = None
    created_at: str
    updated_at: str


class FaqUpdate(BaseModel):
    approved: bool
    alias_active: bool


class EnrichmentJobResponse(BaseModel):
    id: str
    document_id: str
    status: str
    progress: int
    attempts: int
    max_attempts: int
    error: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None


class KnowledgeResponse(BaseModel):
    document: DocumentResponse
    profile: ProfileResponse | None
    faqs: list[FaqResponse]
    job: EnrichmentJobResponse | None


class SessionResponse(BaseModel):
    id: str
    created_at: str
    last_active_at: str
    expires_at: str


class Citation(BaseModel):
    document_id: str
    document: str
    page: int
    excerpt: str
    distance: float


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    rewritten_query: str | None = None
    grounded: bool | None = None
    citations: list[Citation] = []
    suggested_questions: list[str] = []
    created_at: str


class AskRequest(BaseModel):
    session_id: str
    question: str = Field(min_length=2, max_length=4000)


class AskResponse(BaseModel):
    request_id: str
    session_id: str
    answer: str
    grounded: bool
    retrieval_status: Literal["grounded", "not_found"]
    rewritten_query: str | None = None
    citations: list[Citation]
    retrieval_diagnostics: dict | None = None
    suggested_questions: list[str] = []


class DocumentPageResponse(BaseModel):
    items: list[DocumentResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    vector_store: bool
    embedding_model: bool
    llm_provider: Literal["claude", "ollama", "openrouter"]
    llm_configured: bool
    llm_available: bool


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class EvaluationQuestionInput(BaseModel):
    question: str = Field(min_length=2)
    supported: bool
    expected_document_id: str | None = None
    expected_page_start: int | None = Field(None, ge=1)
    expected_page_end: int | None = Field(None, ge=1)
    topic: str | None = None
    reference_answer: str | None = None
    key_points: list[str] = []
    notes: str | None = None
    enabled: bool = True


class EvaluationRunResponse(BaseModel):
    id: str
    dataset_id: str
    status: str
    progress: int
    total_questions: int
    completed_questions: int
    config: dict
    document_versions: dict
    metrics: dict
    passed: bool | None
    error: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
