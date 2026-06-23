import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.fts_available = False
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    rewritten_query TEXT,
                    grounded INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS citations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    document TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    excerpt TEXT NOT NULL,
                    distance REAL NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS question_logs (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    session_id TEXT,
                    question TEXT NOT NULL,
                    rewritten_query TEXT,
                    grounded INTEGER NOT NULL DEFAULT 0,
                    citation_count INTEGER NOT NULL DEFAULT 0,
                    latency_ms INTEGER NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS router_profiles (
                    document_id TEXT PRIMARY KEY,
                    router_name TEXT,
                    model TEXT,
                    product_id TEXT,
                    supported_configuration TEXT,
                    features_json TEXT NOT NULL DEFAULT '[]',
                    topics_json TEXT NOT NULL DEFAULT '[]',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    extracted_values_json TEXT NOT NULL DEFAULT '{}',
                    manual_fields_json TEXT NOT NULL DEFAULT '[]',
                    identifier_aliases_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS generated_faqs (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    expected_topic TEXT,
                    source_chunk_id TEXT NOT NULL,
                    source_page INTEGER NOT NULL,
                    source_excerpt TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    alias_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS faq_evaluations (
                    faq_id TEXT PRIMARY KEY,
                    passed INTEGER NOT NULL,
                    best_distance REAL,
                    retrieved_pages_json TEXT NOT NULL DEFAULT '[]',
                    expected_source_found INTEGER NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    FOREIGN KEY(faq_id) REFERENCES generated_faqs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS enrichment_jobs (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_identifiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    display_value TEXT NOT NULL,
                    normalized_value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(document_id, normalized_value),
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS evaluation_datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluation_questions (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    supported INTEGER NOT NULL,
                    expected_document_id TEXT,
                    expected_page_start INTEGER,
                    expected_page_end INTEGER,
                    topic TEXT,
                    reference_answer TEXT,
                    key_points_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(dataset_id, question),
                    FOREIGN KEY(dataset_id) REFERENCES evaluation_datasets(id) ON DELETE CASCADE,
                    FOREIGN KEY(expected_document_id) REFERENCES documents(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    total_questions INTEGER NOT NULL DEFAULT 0,
                    completed_questions INTEGER NOT NULL DEFAULT 0,
                    config_json TEXT NOT NULL,
                    document_versions_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    passed INTEGER,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY(dataset_id) REFERENCES evaluation_datasets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS evaluation_results (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    diagnostics_json TEXT NOT NULL,
                    top1_correct INTEGER NOT NULL,
                    top3_correct INTEGER NOT NULL,
                    page_correct INTEGER,
                    citation_correct INTEGER NOT NULL,
                    refusal_correct INTEGER NOT NULL,
                    key_point_score REAL,
                    judge_score REAL,
                    judge_explanation TEXT,
                    retrieval_latency_ms INTEGER NOT NULL,
                    answer_latency_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES evaluation_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(question_id) REFERENCES evaluation_questions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_created
                    ON messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_logs_created
                    ON question_logs(created_at);
                CREATE INDEX IF NOT EXISTS idx_faqs_document
                    ON generated_faqs(document_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                    ON enrichment_jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_identifiers_normalized
                    ON document_identifiers(normalized_value);
                CREATE INDEX IF NOT EXISTS idx_eval_runs_status
                    ON evaluation_runs(status, created_at);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(documents)").fetchall()
            }
            additions = {
                "enrichment_status": "TEXT NOT NULL DEFAULT 'not_started'",
                "enrichment_error": "TEXT",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE documents ADD COLUMN {name} {definition}"
                    )
            profile_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(router_profiles)"
                ).fetchall()
            }
            if "identifier_aliases_json" not in profile_columns:
                connection.execute(
                    "ALTER TABLE router_profiles ADD COLUMN "
                    "identifier_aliases_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.execute(
                """
                UPDATE enrichment_jobs
                SET status = 'queued', progress = 0, error = 'Recovered after restart',
                    updated_at = ?
                WHERE status = 'running'
                """,
                (utc_now(),),
            )
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS document_search
                    USING fts5(document_id UNINDEXED, searchable_text)
                    """
                )
                self.fts_available = True
            except sqlite3.OperationalError:
                self.fts_available = False
            connection.execute(
                """
                UPDATE evaluation_runs SET status = 'queued', progress = 0,
                    error = 'Recovered after restart', updated_at = ?
                WHERE status = 'running'
                """,
                (utc_now(),),
            )

    def create_document(self, filename: str, stored_name: str, sha256: str) -> dict[str, Any]:
        document_id = str(uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO documents
                    (id, filename, stored_name, sha256, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'processing', ?, ?)
                """,
                (document_id, filename, stored_name, sha256, now, now),
            )
        self.refresh_document_search(document_id)
        return self.get_document(document_id)

    def update_document(self, document_id: str, **values: Any) -> dict[str, Any]:
        allowed = {
            "status",
            "page_count",
            "chunk_count",
            "error",
            "version",
            "sha256",
            "enrichment_status",
            "enrichment_error",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE documents SET {assignments} WHERE id = ?",
                (*updates.values(), document_id),
            )
        return self.get_document(document_id)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def find_document_by_hash(self, sha256: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone()
        return dict(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM documents ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def search_documents(
        self,
        *,
        search: str = "",
        status: str | None = None,
        enrichment_status: str | None = None,
        feature: str | None = None,
        topic: str | None = None,
        sort: str = "created_at",
        direction: str = "desc",
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        allowed_sort = {
            "created_at": "d.created_at",
            "updated_at": "d.updated_at",
            "filename": "d.filename",
            "status": "d.status",
            "router_name": "p.router_name",
        }
        clauses = []
        params: list[Any] = []
        if search:
            if self.fts_available:
                tokens = re.findall(r"[a-zA-Z0-9]+", search)
                if tokens:
                    clauses.append(
                        "d.id IN (SELECT document_id FROM document_search "
                        "WHERE document_search MATCH ?)"
                    )
                    params.append(" AND ".join(f'"{token}"*' for token in tokens))
            else:
                term = f"%{search.casefold()}%"
                clauses.append(
                    """(
                    lower(d.filename) LIKE ? OR lower(COALESCE(p.router_name,'')) LIKE ?
                    OR lower(COALESCE(p.model,'')) LIKE ?
                    OR lower(COALESCE(p.product_id,'')) LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM document_identifiers i
                        WHERE i.document_id=d.id AND lower(i.display_value) LIKE ?
                    )
                    )"""
                )
                params.extend([term] * 5)
        if status:
            clauses.append("d.status = ?")
            params.append(status)
        if enrichment_status:
            clauses.append("d.enrichment_status = ?")
            params.append(enrichment_status)
        if feature:
            clauses.append("lower(COALESCE(p.features_json,'')) LIKE ?")
            params.append(f"%{feature.casefold()}%")
        if topic:
            clauses.append("lower(COALESCE(p.topics_json,'')) LIKE ?")
            params.append(f"%{topic.casefold()}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = allowed_sort.get(sort, "d.created_at")
        order_direction = "ASC" if direction.lower() == "asc" else "DESC"
        offset = (page - 1) * page_size
        base = (
            " FROM documents d LEFT JOIN router_profiles p ON p.document_id=d.id "
            + where
        )
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*)" + base, params).fetchone()[0]
            rows = connection.execute(
                "SELECT d.*" + base + f" ORDER BY {order} {order_direction} LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
        items = [self.document_summary(dict(row)) for row in rows]
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    def document_summary(self, document: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            profile = connection.execute(
                "SELECT status FROM router_profiles WHERE document_id = ?",
                (document["id"],),
            ).fetchone()
            counts = connection.execute(
                """
                SELECT COUNT(*) AS faq_count,
                       COALESCE(SUM(CASE WHEN e.passed = 1 THEN 1 ELSE 0 END), 0)
                           AS evaluation_pass_count
                FROM generated_faqs f
                LEFT JOIN faq_evaluations e ON e.faq_id = f.id
                WHERE f.document_id = ?
                """,
                (document["id"],),
            ).fetchone()
        result = dict(document)
        result["profile_status"] = (
            profile["status"]
            if profile
            else (
                document.get("enrichment_status", "not_started")
                if document.get("enrichment_status") in {"queued", "running", "failed"}
                else "not_started"
            )
        )
        result["faq_count"] = int(counts["faq_count"])
        result["evaluation_pass_count"] = int(counts["evaluation_pass_count"])
        return result

    def get_indexed_profiles(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.id AS document_id, d.filename, p.*
                FROM documents d
                LEFT JOIN router_profiles p ON p.document_id = d.id
                WHERE d.status = 'indexed'
                ORDER BY d.created_at DESC
                """
            ).fetchall()
        return [self._decode_profile(dict(row)) for row in rows]

    @staticmethod
    def _decode_profile(row: dict[str, Any]) -> dict[str, Any]:
        for key, default in (
            ("features_json", []),
            ("topics_json", []),
            ("provenance_json", {}),
            ("extracted_values_json", {}),
            ("manual_fields_json", []),
            ("identifier_aliases_json", []),
        ):
            row[key.removesuffix("_json")] = json.loads(row.get(key) or json.dumps(default))
            row.pop(key, None)
        return row

    def get_profile(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM router_profiles WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        return self._decode_profile(dict(row)) if row else None

    def upsert_extracted_profile(
        self, document_id: str, values: dict[str, Any], provenance: dict[str, Any]
    ) -> dict[str, Any]:
        current = self.get_profile(document_id)
        manual_fields = set(current["manual_fields"] if current else [])
        extracted_values = {
            key: values.get(key)
            for key in (
                "router_name",
                "model",
                "product_id",
                "supported_configuration",
                "features",
                "topics",
            )
        }
        final = dict(extracted_values)
        if current:
            for field in manual_fields:
                final[field] = current.get(field)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO router_profiles (
                    document_id, router_name, model, product_id,
                    supported_configuration, features_json, topics_json,
                    provenance_json, extracted_values_json, manual_fields_json,
                    identifier_aliases_json,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    router_name = excluded.router_name,
                    model = excluded.model,
                    product_id = excluded.product_id,
                    supported_configuration = excluded.supported_configuration,
                    features_json = excluded.features_json,
                    topics_json = excluded.topics_json,
                    provenance_json = excluded.provenance_json,
                    extracted_values_json = excluded.extracted_values_json,
                    manual_fields_json = excluded.manual_fields_json,
                    identifier_aliases_json = excluded.identifier_aliases_json,
                    status = 'ready',
                    updated_at = excluded.updated_at
                """,
                (
                    document_id,
                    final.get("router_name"),
                    final.get("model"),
                    final.get("product_id"),
                    final.get("supported_configuration"),
                    json.dumps(final.get("features") or []),
                    json.dumps(final.get("topics") or []),
                    json.dumps(provenance),
                    json.dumps(extracted_values),
                    json.dumps(sorted(manual_fields)),
                    json.dumps(current.get("identifier_aliases", []) if current else []),
                    now,
                    now,
                ),
            )
        return self.get_profile(document_id)

    def update_profile(self, document_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        profile = self.get_profile(document_id)
        if not profile:
            raise KeyError(document_id)
        allowed = {
            "router_name",
            "model",
            "product_id",
            "supported_configuration",
            "features",
            "topics",
            "identifier_aliases",
        }
        updates = {key: value for key, value in changes.items() if key in allowed}
        manual_fields = set(profile["manual_fields"])
        manual_fields.update(updates)
        assignments = []
        params: list[Any] = []
        for key, value in updates.items():
            column = (
                f"{key}_json"
                if key in {"features", "topics", "identifier_aliases"}
                else key
            )
            assignments.append(f"{column} = ?")
            params.append(
                json.dumps(value)
                if key in {"features", "topics", "identifier_aliases"}
                else value
            )
        assignments.extend(["manual_fields_json = ?", "updated_at = ?"])
        params.extend([json.dumps(sorted(manual_fields)), utc_now(), document_id])
        with self.connect() as connection:
            connection.execute(
                f"UPDATE router_profiles SET {', '.join(assignments)} "
                "WHERE document_id = ?",
                params,
            )
        return self.get_profile(document_id)

    def replace_document_identifiers(
        self, document_id: str, identifiers: list[tuple[str, str]]
    ) -> None:
        from .identifiers import normalize_identifier

        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM document_identifiers WHERE document_id = ?",
                (document_id,),
            )
            for source, value in identifiers:
                normalized = normalize_identifier(value)
                if normalized:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO document_identifiers
                            (document_id, source, display_value, normalized_value, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (document_id, source, value, normalized, now),
                    )
        self.refresh_document_search(document_id)

    def refresh_document_search(self, document_id: str) -> None:
        if not self.fts_available:
            return
        document = self.get_document(document_id)
        if not document:
            return
        profile = self.get_profile(document_id) or {}
        with self.connect() as connection:
            identifiers = connection.execute(
                "SELECT display_value FROM document_identifiers WHERE document_id=?",
                (document_id,),
            ).fetchall()
            text = " ".join(
                [
                    document["filename"],
                    profile.get("router_name") or "",
                    profile.get("model") or "",
                    profile.get("product_id") or "",
                    " ".join(profile.get("features") or []),
                    " ".join(profile.get("topics") or []),
                    " ".join(row["display_value"] for row in identifiers),
                ]
            )
            connection.execute(
                "DELETE FROM document_search WHERE document_id=?", (document_id,)
            )
            connection.execute(
                "INSERT INTO document_search(document_id, searchable_text) VALUES (?,?)",
                (document_id, text),
            )

    def list_identifiers(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT i.*, d.filename FROM document_identifiers i
                JOIN documents d ON d.id=i.document_id
                WHERE d.status='indexed'
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_evaluation_dataset(self, name: str, description: str | None) -> dict:
        dataset_id = str(uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_datasets
                    (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (dataset_id, name, description, now, now),
            )
        return self.get_evaluation_dataset(dataset_id)

    def list_evaluation_datasets(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.*, COUNT(q.id) AS question_count
                FROM evaluation_datasets d
                LEFT JOIN evaluation_questions q ON q.dataset_id=d.id
                GROUP BY d.id ORDER BY d.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_evaluation_dataset(self, dataset_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_datasets WHERE id=?", (dataset_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_evaluation_dataset(self, dataset_id: str, changes: dict) -> dict:
        allowed = {k: v for k, v in changes.items() if k in {"name", "description"}}
        allowed["updated_at"] = utc_now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE evaluation_datasets SET "
                + ", ".join(f"{key}=?" for key in allowed)
                + " WHERE id=?",
                [*allowed.values(), dataset_id],
            )
        return self.get_evaluation_dataset(dataset_id)

    def delete_evaluation_dataset(self, dataset_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM evaluation_datasets WHERE id=?", (dataset_id,)
            )
        return cursor.rowcount > 0

    def add_evaluation_question(self, dataset_id: str, values: dict) -> dict:
        question_id = str(uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_questions (
                    id, dataset_id, question, supported, expected_document_id,
                    expected_page_start, expected_page_end, topic, reference_answer,
                    key_points_json, notes, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    dataset_id,
                    values["question"],
                    int(values["supported"]),
                    values.get("expected_document_id"),
                    values.get("expected_page_start"),
                    values.get("expected_page_end"),
                    values.get("topic"),
                    values.get("reference_answer"),
                    json.dumps(values.get("key_points") or []),
                    values.get("notes"),
                    int(values.get("enabled", True)),
                    now,
                    now,
                ),
            )
        return self.get_evaluation_question(question_id)

    def get_evaluation_question(self, question_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_questions WHERE id=?", (question_id,)
            ).fetchone()
        return self._decode_evaluation_question(dict(row)) if row else None

    @staticmethod
    def _decode_evaluation_question(item: dict) -> dict:
        item["supported"] = bool(item["supported"])
        item["enabled"] = bool(item["enabled"])
        item["key_points"] = json.loads(item.pop("key_points_json") or "[]")
        return item

    def list_evaluation_questions(self, dataset_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evaluation_questions WHERE dataset_id=? "
                "ORDER BY created_at",
                (dataset_id,),
            ).fetchall()
        return [self._decode_evaluation_question(dict(row)) for row in rows]

    def update_evaluation_question(self, question_id: str, changes: dict) -> dict:
        mapping = {
            "question": "question",
            "supported": "supported",
            "expected_document_id": "expected_document_id",
            "expected_page_start": "expected_page_start",
            "expected_page_end": "expected_page_end",
            "topic": "topic",
            "reference_answer": "reference_answer",
            "key_points": "key_points_json",
            "notes": "notes",
            "enabled": "enabled",
        }
        updates = []
        params = []
        for key, column in mapping.items():
            if key in changes:
                value = changes[key]
                if key == "key_points":
                    value = json.dumps(value or [])
                if key in {"supported", "enabled"}:
                    value = int(value)
                updates.append(f"{column}=?")
                params.append(value)
        updates.append("updated_at=?")
        params.extend([utc_now(), question_id])
        with self.connect() as connection:
            connection.execute(
                f"UPDATE evaluation_questions SET {', '.join(updates)} WHERE id=?",
                params,
            )
        return self.get_evaluation_question(question_id)

    def delete_evaluation_question(self, question_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM evaluation_questions WHERE id=?", (question_id,)
            )
        return cursor.rowcount > 0

    def create_evaluation_run(
        self, dataset_id: str, config: dict, document_versions: dict
    ) -> dict:
        run_id = str(uuid4())
        now = utc_now()
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM evaluation_questions "
                "WHERE dataset_id=? AND enabled=1",
                (dataset_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO evaluation_runs (
                    id, dataset_id, status, total_questions, config_json,
                    document_versions_json, created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    dataset_id,
                    total,
                    json.dumps(config),
                    json.dumps(document_versions),
                    now,
                    now,
                ),
            )
        return self.get_evaluation_run(run_id)

    def get_evaluation_run(self, run_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_runs WHERE id=?", (run_id,)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        for key in ("config_json", "document_versions_json", "metrics_json"):
            item[key.removesuffix("_json")] = json.loads(item.pop(key) or "{}")
        item["passed"] = None if item["passed"] is None else bool(item["passed"])
        return item

    def claim_evaluation_run(self) -> dict | None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM evaluation_runs WHERE status='queued' "
                "ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            cursor = connection.execute(
                "UPDATE evaluation_runs SET status='running', started_at=?, "
                "updated_at=? WHERE id=? AND status='queued'",
                (now, now, row["id"]),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_evaluation_run(row["id"])

    def save_evaluation_result(self, run_id: str, question_id: str, result: dict) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_results (
                    id, run_id, question_id, answer, citations_json,
                    diagnostics_json, top1_correct, top3_correct, page_correct,
                    citation_correct, refusal_correct, key_point_score, judge_score,
                    judge_explanation, retrieval_latency_ms, answer_latency_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    run_id,
                    question_id,
                    result["answer"],
                    json.dumps(result["citations"]),
                    json.dumps(result["diagnostics"]),
                    int(result["top1_correct"]),
                    int(result["top3_correct"]),
                    None if result["page_correct"] is None else int(result["page_correct"]),
                    int(result["citation_correct"]),
                    int(result["refusal_correct"]),
                    result["key_point_score"],
                    result.get("judge_score"),
                    result.get("judge_explanation"),
                    result["retrieval_latency_ms"],
                    result["answer_latency_ms"],
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE evaluation_runs SET completed_questions=completed_questions+1,
                    progress=CAST((completed_questions+1)*100.0/total_questions AS INTEGER),
                    updated_at=? WHERE id=?
                """,
                (now, run_id),
            )

    def list_evaluation_results(self, run_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT r.*, q.question, q.supported, q.expected_document_id,
                       q.expected_page_start, q.expected_page_end, q.topic
                FROM evaluation_results r
                JOIN evaluation_questions q ON q.id=r.question_id
                WHERE r.run_id=? ORDER BY r.created_at
                """,
                (run_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["citations"] = json.loads(item.pop("citations_json"))
            item["diagnostics"] = json.loads(item.pop("diagnostics_json"))
            for key in (
                "supported", "top1_correct", "top3_correct", "citation_correct",
                "refusal_correct",
            ):
                item[key] = bool(item[key])
            item["page_correct"] = (
                None if item["page_correct"] is None else bool(item["page_correct"])
            )
            items.append(item)
        return items

    def complete_evaluation_run(self, run_id: str, metrics: dict, passed: bool) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE evaluation_runs SET status='completed', progress=100,
                    metrics_json=?, passed=?, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (json.dumps(metrics), int(passed), now, now, run_id),
            )

    def fail_evaluation_run(self, run_id: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE evaluation_runs SET status='failed', error=?, updated_at=? "
                "WHERE id=?",
                (error[:500], utc_now(), run_id),
            )

    def replace_faqs(self, document_id: str, faqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM generated_faqs WHERE document_id = ?", (document_id,)
            )
            for faq in faqs:
                connection.execute(
                    """
                    INSERT INTO generated_faqs (
                        id, document_id, question, expected_topic, source_chunk_id,
                        source_page, source_excerpt, approved, alias_active,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                    """,
                    (
                        faq["id"],
                        document_id,
                        faq["question"],
                        faq.get("expected_topic"),
                        faq["source_chunk_id"],
                        faq["source_page"],
                        faq["source_excerpt"],
                        now,
                        now,
                    ),
                )
        return self.list_faqs(document_id)

    def list_faqs(self, document_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT f.*, e.passed, e.best_distance, e.retrieved_pages_json,
                       e.expected_source_found, e.evaluated_at
                FROM generated_faqs f
                LEFT JOIN faq_evaluations e ON e.faq_id = f.id
                WHERE f.document_id = ?
                ORDER BY f.created_at, f.question
                """,
                (document_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["approved"] = bool(item["approved"])
            item["alias_active"] = bool(item["alias_active"])
            item["passed"] = None if item["passed"] is None else bool(item["passed"])
            item["expected_source_found"] = (
                None
                if item["expected_source_found"] is None
                else bool(item["expected_source_found"])
            )
            item["retrieved_pages"] = json.loads(item.pop("retrieved_pages_json") or "[]")
            result.append(item)
        return result

    def get_faq(self, faq_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM generated_faqs WHERE id = ?", (faq_id,)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["approved"] = bool(item["approved"])
        item["alias_active"] = bool(item["alias_active"])
        return item

    def update_faq(self, faq_id: str, approved: bool, alias_active: bool) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE generated_faqs
                SET approved = ?, alias_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (int(approved), int(alias_active), utc_now(), faq_id),
            )
        return self.get_faq(faq_id)

    def save_faq_evaluation(
        self,
        faq_id: str,
        *,
        passed: bool,
        best_distance: float | None,
        retrieved_pages: list[int],
        expected_source_found: bool,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO faq_evaluations (
                    faq_id, passed, best_distance, retrieved_pages_json,
                    expected_source_found, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(faq_id) DO UPDATE SET
                    passed = excluded.passed,
                    best_distance = excluded.best_distance,
                    retrieved_pages_json = excluded.retrieved_pages_json,
                    expected_source_found = excluded.expected_source_found,
                    evaluated_at = excluded.evaluated_at
                """,
                (
                    faq_id,
                    int(passed),
                    best_distance,
                    json.dumps(retrieved_pages),
                    int(expected_source_found),
                    utc_now(),
                ),
            )

    def create_enrichment_job(self, document_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            active = connection.execute(
                """
                SELECT * FROM enrichment_jobs
                WHERE document_id = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            if active:
                return dict(active)
            job_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO enrichment_jobs (
                    id, document_id, status, progress, attempts, max_attempts,
                    created_at, updated_at
                ) VALUES (?, ?, 'queued', 0, 0, 3, ?, ?)
                """,
                (job_id, document_id, now, now),
            )
            connection.execute(
                """
                UPDATE documents
                SET enrichment_status = 'queued', enrichment_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, document_id),
            )
        return self.get_enrichment_job(job_id)

    def cancel_active_enrichment_jobs(self, document_id: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE enrichment_jobs
                SET status = 'cancelled', error = 'Superseded by document re-index',
                    updated_at = ?
                WHERE document_id = ? AND status IN ('queued', 'running')
                """,
                (now, document_id),
            )

    def invalidate_document_enrichment(self, document_id: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM generated_faqs WHERE document_id = ?", (document_id,)
            )
            connection.execute(
                """
                UPDATE router_profiles SET status = 'pending', updated_at = ?
                WHERE document_id = ?
                """,
                (now, document_id),
            )
            connection.execute(
                """
                UPDATE documents SET enrichment_status = 'not_started',
                    enrichment_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, document_id),
            )

    def get_enrichment_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM enrichment_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def claim_next_enrichment_job(self) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM enrichment_jobs
                WHERE status = 'queued' AND attempts < max_attempts
                ORDER BY created_at LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            cursor = connection.execute(
                """
                UPDATE enrichment_jobs
                SET status = 'running', attempts = attempts + 1,
                    started_at = ?, updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, row["id"]),
            )
            if cursor.rowcount != 1:
                return None
            connection.execute(
                """
                UPDATE documents SET enrichment_status = 'running',
                    enrichment_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, row["document_id"]),
            )
        return self.get_enrichment_job(row["id"])

    def update_enrichment_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        job = self.get_enrichment_job(job_id)
        if not job:
            raise KeyError(job_id)
        now = utc_now()
        updates = ["updated_at = ?"]
        params: list[Any] = [now]
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if error is not None or status in {"completed", "failed", "queued"}:
            updates.append("error = ?")
            params.append(error)
        if status == "completed":
            updates.append("completed_at = ?")
            params.append(now)
        params.append(job_id)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE enrichment_jobs SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            document_status = {
                "queued": "queued",
                "running": "running",
                "completed": "ready",
                "failed": "failed",
            }.get(status)
            if document_status:
                connection.execute(
                    """
                    UPDATE documents
                    SET enrichment_status = ?, enrichment_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (document_status, error, now, job["document_id"]),
                )
        return self.get_enrichment_job(job_id)

    def retry_or_fail_enrichment_job(self, job_id: str, error: str) -> dict[str, Any]:
        job = self.get_enrichment_job(job_id)
        next_status = "queued" if job["attempts"] < job["max_attempts"] else "failed"
        return self.update_enrichment_job(
            job_id, status=next_status, progress=0, error=error
        )

    def get_knowledge(self, document_id: str) -> dict[str, Any]:
        document = self.get_document(document_id)
        if not document:
            raise KeyError(document_id)
        with self.connect() as connection:
            job_row = connection.execute(
                """
                SELECT * FROM enrichment_jobs WHERE document_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        return {
            "document": self.document_summary(document),
            "profile": self.get_profile(document_id),
            "faqs": self.list_faqs(document_id),
            "job": dict(job_row) if job_row else None,
        }

    def delete_document(self, document_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def create_session(self, ttl_minutes: int) -> dict[str, Any]:
        session_id = str(uuid4())
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        expires = (now_dt + timedelta(minutes=ttl_minutes)).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_sessions (id, created_at, last_active_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, now, now, expires),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def touch_session(self, session_id: str, ttl_minutes: int) -> None:
        now_dt = datetime.now(UTC)
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE chat_sessions
                SET last_active_at = ?, expires_at = ?
                WHERE id = ?
                """,
                (
                    now_dt.isoformat(),
                    (now_dt + timedelta(minutes=ttl_minutes)).isoformat(),
                    session_id,
                ),
            )

    def delete_session(self, session_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM chat_sessions WHERE id = ?", (session_id,)
            )
        return cursor.rowcount > 0

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        rewritten_query: str | None = None,
        grounded: bool | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        message_id = str(uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages
                    (id, session_id, role, content, rewritten_query, grounded, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    role,
                    content,
                    rewritten_query,
                    None if grounded is None else int(grounded),
                    now,
                ),
            )
            for citation in citations or []:
                connection.execute(
                    """
                    INSERT INTO citations
                        (message_id, document_id, document, page, excerpt, distance)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        citation["document_id"],
                        citation["document"],
                        citation["page"],
                        citation["excerpt"],
                        citation["distance"],
                    ),
                )
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "rewritten_query": rewritten_query,
            "grounded": grounded,
            "citations": citations or [],
            "created_at": now,
        }

    def get_messages(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT rowid AS _rowid, * FROM messages
                    WHERE session_id = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT ?
                ) ORDER BY created_at ASC, _rowid ASC
                """,
                (session_id, limit),
            ).fetchall()
            messages = []
            for row in rows:
                item = dict(row)
                item["grounded"] = (
                    None if item["grounded"] is None else bool(item["grounded"])
                )
                citation_rows = connection.execute(
                    "SELECT document_id, document, page, excerpt, distance "
                    "FROM citations WHERE message_id = ? ORDER BY id",
                    (item["id"],),
                ).fetchall()
                item["citations"] = [dict(citation) for citation in citation_rows]
                messages.append(item)
        return messages

    def add_question_log(self, **values: Any) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO question_logs
                    (id, request_id, session_id, question, rewritten_query, grounded,
                     citation_count, latency_ms, error_code, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    values["request_id"],
                    values.get("session_id"),
                    values["question"],
                    values.get("rewritten_query"),
                    int(values.get("grounded", False)),
                    values.get("citation_count", 0),
                    values["latency_ms"],
                    values.get("error_code"),
                    utc_now(),
                ),
            )

    def healthcheck(self) -> bool:
        try:
            with self.connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False
