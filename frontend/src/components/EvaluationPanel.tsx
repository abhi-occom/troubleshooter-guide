import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type {
  DocumentRecord,
  EvaluationDataset,
  EvaluationRun,
} from "../types";

interface Props {
  documents: DocumentRecord[];
  onError: (error: unknown) => void;
}

export function EvaluationPanel({ documents, onError }: Props) {
  const [documentOptions, setDocumentOptions] = useState(documents);
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [selected, setSelected] = useState<EvaluationDataset | null>(null);
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");
  const [expectedDocument, setExpectedDocument] = useState("");
  const [supported, setSupported] = useState(true);
  const [topic, setTopic] = useState("");
  const [referenceAnswer, setReferenceAnswer] = useState("");
  const [keyPoints, setKeyPoints] = useState("");
  const [pageStart, setPageStart] = useState("");
  const [pageEnd, setPageEnd] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = async (datasetId?: string) => {
    const all = await api.listDatasets();
    setDatasets(all);
    const id = datasetId ?? selected?.id;
    if (id) setSelected(await api.getDataset(id));
  };

  useEffect(() => {
    void reload().catch(onError);
    void api
      .listDocuments({ page_size: 100, sort: "filename", direction: "asc" })
      .then((page) => setDocumentOptions(page.items))
      .catch(onError);
  }, []);

  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getEvaluationRun(run.id);
        setRun(next);
        if (next.status === "completed") {
          setResults(await api.getEvaluationResults(next.id));
        }
      } catch (error) {
        onError(error);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status]);

  const createDataset = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const created = await api.createDataset(name);
      setName("");
      await reload(created.id);
    } catch (error) {
      onError(error);
    }
  };

  const addQuestion = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    try {
      await api.addEvaluationQuestion(selected.id, {
        question,
        supported,
        expected_document_id: supported ? expectedDocument : null,
        expected_page_start: pageStart ? Number(pageStart) : null,
        expected_page_end: pageEnd ? Number(pageEnd) : null,
        topic: topic || null,
        reference_answer: referenceAnswer || null,
        key_points: keyPoints
          .split("|")
          .map((item) => item.trim())
          .filter(Boolean),
        notes: null,
        enabled: true,
      });
      setQuestion("");
      setTopic("");
      setReferenceAnswer("");
      setKeyPoints("");
      setPageStart("");
      setPageEnd("");
      await reload(selected.id);
    } catch (error) {
      onError(error);
    }
  };

  return (
    <section className="evaluation-panel">
      <h3>Retrieval evaluation</h3>
      <form onSubmit={createDataset}>
        <input
          aria-label="Dataset name"
          placeholder="New dataset name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button disabled={!name.trim()}>Create</button>
      </form>
      <select
        aria-label="Evaluation dataset"
        value={selected?.id ?? ""}
        onChange={(event) =>
          void api
            .getDataset(event.target.value)
            .then(setSelected)
            .catch(onError)
        }
      >
        <option value="">Select dataset</option>
        {datasets.map((dataset) => (
          <option key={dataset.id} value={dataset.id}>
            {dataset.name} ({dataset.question_count ?? 0})
          </option>
        ))}
      </select>

      {selected && (
        <>
          <div className="evaluation-actions">
            <input
              aria-label="Selected dataset name"
              value={selected.name}
              onChange={(event) =>
                setSelected({ ...selected, name: event.target.value })
              }
            />
            <button
              onClick={() =>
                void api
                  .updateDataset(selected.id, { name: selected.name })
                  .then(() => reload(selected.id))
                  .catch(onError)
              }
            >
              Save dataset
            </button>
            <button
              onClick={() =>
                void api
                  .deleteDataset(selected.id)
                  .then(() => {
                    setSelected(null);
                    return reload();
                  })
                  .catch(onError)
              }
            >
              Delete dataset
            </button>
          </div>
          <form className="evaluation-question-form" onSubmit={addQuestion}>
            <textarea
              aria-label="Evaluation question"
              placeholder="Real support question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <label>
              <input
                type="checkbox"
                checked={supported}
                onChange={(event) => setSupported(event.target.checked)}
              />
              Supported by manuals
            </label>
            {supported && (
              <>
                <select
                  aria-label="Expected document"
                  value={expectedDocument}
                  onChange={(event) => setExpectedDocument(event.target.value)}
                >
                  <option value="">Expected document</option>
                  {documentOptions.map((document) => (
                    <option key={document.id} value={document.id}>
                      {document.filename}
                    </option>
                  ))}
                </select>
                <div>
                  <input
                    aria-label="Expected page start"
                    type="number"
                    min="1"
                    placeholder="Page start"
                    value={pageStart}
                    onChange={(event) => setPageStart(event.target.value)}
                  />
                  <input
                    aria-label="Expected page end"
                    type="number"
                    min="1"
                    placeholder="Page end"
                    value={pageEnd}
                    onChange={(event) => setPageEnd(event.target.value)}
                  />
                </div>
              </>
            )}
            <input
              aria-label="Question topic"
              placeholder="Topic"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
            />
            <textarea
              aria-label="Reference answer"
              placeholder="Optional reference answer"
              value={referenceAnswer}
              onChange={(event) => setReferenceAnswer(event.target.value)}
            />
            <input
              aria-label="Required key points"
              placeholder="Key points separated by |"
              value={keyPoints}
              onChange={(event) => setKeyPoints(event.target.value)}
            />
            <button disabled={!question.trim() || (supported && !expectedDocument)}>
              Add question
            </button>
          </form>
          <div className="evaluation-actions">
            <input
              ref={fileRef}
              hidden
              type="file"
              accept=".csv,text/csv"
              onChange={async (event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                try {
                  await api.importEvaluationCsv(selected.id, file);
                  await reload(selected.id);
                } catch (error) {
                  onError(error);
                }
              }}
            />
            <button onClick={() => fileRef.current?.click()}>Import CSV</button>
            <a href={`/api/evaluation/datasets/${selected.id}/export`}>
              Export CSV
            </a>
            <button
              onClick={() =>
                void api
                  .createEvaluationRun(selected.id)
                  .then((next) => {
                    setRun(next);
                    setResults([]);
                  })
                  .catch(onError)
              }
            >
              Run evaluation
            </button>
          </div>
          <div className="evaluation-question-list">
            {(selected.questions ?? []).map((item) => (
              <div key={item.id}>
                <span>{item.question}</span>
                <label>
                  <input
                    type="checkbox"
                    checked={item.enabled}
                    onChange={(event) =>
                      void api
                        .updateEvaluationQuestion(item.id, {
                          enabled: event.target.checked,
                        })
                        .then(() => reload(selected.id))
                        .catch(onError)
                    }
                  />
                  Enabled
                </label>
                <button
                  onClick={() =>
                    void api
                      .deleteEvaluationQuestion(item.id)
                      .then(() => reload(selected.id))
                      .catch(onError)
                  }
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {run && (
        <div className="evaluation-run">
          <strong>
            {run.status} · {run.progress}%
          </strong>
          {run.status === "completed" && (
            <>
              <span className={run.passed ? "run-pass" : "run-fail"}>
                {run.passed ? "Passed" : "Failed"}
              </span>
              <p>
                Top-3:{" "}
                {Math.round(Number(run.metrics.top3_accuracy ?? 0) * 100)}% ·
                Citations/refusals:{" "}
                {Math.round(
                  Number(run.metrics.citation_refusal_accuracy ?? 0) * 100,
                )}
                %
              </p>
              <details>
                <summary>Question results ({results.length})</summary>
                {results.map((result) => (
                  <div className="evaluation-result" key={String(result.id)}>
                    <strong>{String(result.question)}</strong>
                    <span>
                      Top-3: {String(result.top3_correct)} · Citation:{" "}
                      {String(result.citation_correct)}
                    </span>
                  </div>
                ))}
              </details>
            </>
          )}
        </div>
      )}
    </section>
  );
}
