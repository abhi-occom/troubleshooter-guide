import threading
import time
from typing import Any

from .llm import NOT_FOUND_ANSWER


class EvaluationService:
    def __init__(self, services: Any):
        self.services = services
        self.database = services.database

    def process_run(self, run: dict) -> None:
        questions = [
            item
            for item in self.database.list_evaluation_questions(run["dataset_id"])
            if item["enabled"]
        ]
        for question in questions:
            retrieval_started = time.perf_counter()
            citations, diagnostics = self.services.retrieve(question["question"])
            retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)
            answer_started = time.perf_counter()
            if citations:
                answer = self.services.provider.answer(
                    question["question"], question["question"], [], citations
                )
            else:
                answer = NOT_FOUND_ANSWER
            answer_ms = int((time.perf_counter() - answer_started) * 1000)

            expected = question["expected_document_id"]
            document_ids = [item["document_id"] for item in citations]
            top1 = bool(expected and document_ids[:1] == [expected])
            top3 = bool(expected and expected in document_ids[:3])
            page_correct = None
            if question["supported"] and question["expected_page_start"] is not None:
                end = question["expected_page_end"] or question["expected_page_start"]
                page_correct = any(
                    item["document_id"] == expected
                    and question["expected_page_start"] <= item["page"] <= end
                    for item in citations
                )
            citation_correct = (
                bool(citations)
                and all(item["document_id"] == expected for item in citations)
                if question["supported"]
                else not citations
            )
            refusal_correct = (
                answer.strip() == NOT_FOUND_ANSWER
                if not question["supported"]
                else answer.strip() != NOT_FOUND_ANSWER
            )
            key_points = question["key_points"]
            key_score = None
            if key_points:
                lowered = answer.casefold()
                key_score = sum(point.casefold() in lowered for point in key_points) / len(
                    key_points
                )
            judge = None
            if question.get("reference_answer"):
                try:
                    judge = self.services.provider.judge_answer(
                        question["question"],
                        answer,
                        question["reference_answer"],
                        "\n".join(item["excerpt"] for item in citations),
                    )
                except Exception:
                    judge = None
            self.database.save_evaluation_result(
                run["id"],
                question["id"],
                {
                    "answer": answer,
                    "citations": citations,
                    "diagnostics": diagnostics,
                    "top1_correct": top1,
                    "top3_correct": top3,
                    "page_correct": page_correct,
                    "citation_correct": citation_correct,
                    "refusal_correct": refusal_correct,
                    "key_point_score": key_score,
                    "judge_score": judge["score"] if judge else None,
                    "judge_explanation": judge["explanation"] if judge else None,
                    "retrieval_latency_ms": retrieval_ms,
                    "answer_latency_ms": answer_ms,
                },
            )
        results = self.database.list_evaluation_results(run["id"])
        supported = [item for item in results if item["supported"]]
        top3 = (
            sum(item["top3_correct"] for item in supported) / len(supported)
            if supported
            else 1.0
        )
        citation_refusal = (
            sum(
                item["citation_correct"] if item["supported"] else item["refusal_correct"]
                for item in results
            )
            / len(results)
            if results
            else 0.0
        )
        metrics = {
            "top1_accuracy": (
                sum(item["top1_correct"] for item in supported) / len(supported)
                if supported
                else 1.0
            ),
            "top3_accuracy": top3,
            "citation_refusal_accuracy": citation_refusal,
            "average_key_point_score": self._average(results, "key_point_score"),
            "average_judge_score": self._average(results, "judge_score"),
            "average_retrieval_latency_ms": self._average(
                results, "retrieval_latency_ms"
            ),
            "average_answer_latency_ms": self._average(results, "answer_latency_ms"),
        }
        self.database.complete_evaluation_run(
            run["id"], metrics, top3 >= 0.90 and citation_refusal >= 0.95
        )

    @staticmethod
    def _average(items: list[dict], key: str) -> float | None:
        values = [item[key] for item in items if item.get(key) is not None]
        return sum(values) / len(values) if values else None

    def run_once(self) -> bool:
        run = self.database.claim_evaluation_run()
        if not run:
            return False
        try:
            self.process_run(run)
        except Exception as exc:
            self.database.fail_evaluation_run(
                run["id"], f"{type(exc).__name__}: {exc}"
            )
        return True


class EvaluationWorker:
    def __init__(self, service: EvaluationService, poll_seconds: float = 2):
        self.service = service
        self.poll_seconds = poll_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._run, name="evaluation-worker", daemon=True
        )
        self.thread.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            if not self.service.run_once():
                self.stop_event.wait(self.poll_seconds)

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
