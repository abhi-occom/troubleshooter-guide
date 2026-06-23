from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .pdf_service import TextChunk


class VectorStore:
    def __init__(self, path: Path, collection_name: str):
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))
        self.embedding_function = DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    def add_document(
        self, document_id: str, filename: str, chunks: list[TextChunk]
    ) -> int:
        self.delete_document(document_id)
        if not chunks:
            return 0
        self.collection.add(
            ids=[f"{document_id}:{chunk.page}:{chunk.chunk_index}" for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "document_id": document_id,
                    "document": filename,
                    "page": chunk.page,
                    "chunk_index": chunk.chunk_index,
                    "record_type": "source",
                }
                for chunk in chunks
            ],
        )
        return len(chunks)

    def delete_document(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})

    def get_document_chunks(self, document_id: str) -> list[dict[str, Any]]:
        result = self.collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        chunks = []
        for record_id, document, metadata in zip(
            result.get("ids", []),
            result.get("documents", []),
            result.get("metadatas", []),
        ):
            if metadata.get("record_type", "source") != "source":
                continue
            chunks.append(
                {
                    "id": record_id,
                    "document_id": document_id,
                    "document": metadata["document"],
                    "page": int(metadata["page"]),
                    "chunk_index": int(metadata.get("chunk_index", 0)),
                    "text": document,
                }
            )
        return sorted(chunks, key=lambda item: (item["page"], item["chunk_index"]))

    def add_faq_alias(
        self,
        faq_id: str,
        document_id: str,
        question: str,
        source_chunk_id: str,
        source_page: int,
        filename: str,
    ) -> None:
        self.delete_faq_alias(faq_id)
        self.collection.add(
            ids=[f"faq:{faq_id}"],
            documents=[question],
            metadatas=[
                {
                    "record_type": "faq_alias",
                    "faq_id": faq_id,
                    "document_id": document_id,
                    "document": filename,
                    "page": source_page,
                    "source_chunk_id": source_chunk_id,
                }
            ],
        )

    def delete_faq_alias(self, faq_id: str) -> None:
        self.collection.delete(ids=[f"faq:{faq_id}"])

    def _source_from_id(
        self, source_chunk_id: str, alias_distance: float
    ) -> dict[str, Any] | None:
        result = self.collection.get(
            ids=[source_chunk_id],
            include=["documents", "metadatas"],
        )
        if not result.get("ids"):
            return None
        metadata = result["metadatas"][0]
        return {
            "source_chunk_id": source_chunk_id,
            "document_id": metadata["document_id"],
            "document": metadata["document"],
            "page": int(metadata["page"]),
            "excerpt": result["documents"][0],
            "distance": float(alias_distance),
        }

    def query(
        self,
        text: str,
        top_k: int,
        max_distance: float,
        *,
        include_aliases: bool = True,
        document_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            return []
        where = (
            {"document_id": {"$in": document_ids}}
            if document_ids
            else None
        )
        result = self.collection.query(
            query_texts=[text],
            n_results=min(top_k * 2 if include_aliases else top_k, self.collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        ids = result.get("ids", [[]])[0]
        matches = []
        for record_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            if distance > max_distance:
                continue
            record_type = metadata.get("record_type", "source")
            if record_type == "faq_alias":
                if not include_aliases:
                    continue
                match = self._source_from_id(metadata["source_chunk_id"], distance)
                if match:
                    match["matched_via_faq_alias"] = metadata["faq_id"]
                    matches.append(match)
            else:
                matches.append(
                    {
                        "source_chunk_id": record_id,
                        "document_id": metadata["document_id"],
                        "document": metadata["document"],
                        "page": int(metadata["page"]),
                        "excerpt": document,
                        "distance": float(distance),
                    }
                )
        deduplicated = []
        seen = set()
        for match in sorted(matches, key=lambda item: item["distance"]):
            key = (match["document_id"], match["page"], match["excerpt"])
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(match)
            if len(deduplicated) >= top_k:
                break
        return deduplicated

    def healthcheck(self) -> bool:
        try:
            self.collection.count()
            return True
        except Exception:
            return False
