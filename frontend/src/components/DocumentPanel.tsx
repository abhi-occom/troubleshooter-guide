import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  LoaderCircle,
  RefreshCw,
  Trash2,
  Upload,
  ChevronDown,
} from "lucide-react";
import { useRef, useState } from "react";
import type { DocumentRecord } from "../types";
import { KnowledgePanel } from "./KnowledgePanel";
import { EvaluationPanel } from "./EvaluationPanel";

interface Props {
  documents: DocumentRecord[];
  loading: boolean;
  onUpload: (file: File) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onReindex: (id: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  onError: (error: unknown) => void;
  pageInfo: { page: number; total: number; total_pages: number };
  filters: Record<string, string | number>;
  onFiltersChange: (filters: Record<string, string | number>) => void;
}

const statusLabels: Record<DocumentRecord["status"], string> = {
  processing: "Indexing",
  indexed: "Ready",
  requires_ocr: "OCR needed",
  failed: "Failed",
};

function StatusIcon({ status }: { status: DocumentRecord["status"] }) {
  if (status === "indexed") return <CheckCircle2 size={15} />;
  if (status === "processing")
    return <LoaderCircle size={15} className="spin" />;
  return <AlertTriangle size={15} />;
}

export function DocumentPanel({
  documents,
  loading,
  onUpload,
  onDelete,
  onReindex,
  onRefresh,
  onError,
  pageInfo,
  filters,
  onFiltersChange,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showEvaluations, setShowEvaluations] = useState(false);

  const chooseFile = async (file?: File) => {
    if (!file) return;
    setUploading(true);
    try {
      await onUpload(file);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const run = async (id: string, action: (id: string) => Promise<void>) => {
    setBusyId(id);
    try {
      await action(id);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <aside className="document-panel">
      <div className="brand">
        <div className="brand-mark">R</div>
        <div>
          <strong>Router Guide AI</strong>
          <span>Grounded support</span>
        </div>
      </div>

      <div className="panel-heading">
        <div>
          <p className="eyebrow">Knowledge base</p>
          <h2>Router manuals</h2>
        </div>
        <span className="count">{pageInfo.total}</span>
      </div>

      <div className="document-filters">
        <input
          aria-label="Search documents"
          placeholder="Search model, product ID…"
          value={String(filters.search ?? "")}
          onChange={(event) =>
            onFiltersChange({ ...filters, search: event.target.value, page: 1 })
          }
        />
        <div>
          <select
            aria-label="Document status"
            value={String(filters.document_status ?? "")}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                document_status: event.target.value,
                page: 1,
              })
            }
          >
            <option value="">All document states</option>
            <option value="indexed">Ready</option>
            <option value="processing">Processing</option>
            <option value="requires_ocr">OCR needed</option>
            <option value="failed">Failed</option>
          </select>
          <select
            aria-label="Enrichment status"
            value={String(filters.enrichment_status ?? "")}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                enrichment_status: event.target.value,
                page: 1,
              })
            }
          >
            <option value="">All knowledge states</option>
            <option value="ready">Knowledge ready</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div>
          <input
            aria-label="Filter by feature"
            placeholder="Feature"
            value={String(filters.feature ?? "")}
            onChange={(event) =>
              onFiltersChange({ ...filters, feature: event.target.value, page: 1 })
            }
          />
          <input
            aria-label="Filter by topic"
            placeholder="Topic"
            value={String(filters.topic ?? "")}
            onChange={(event) =>
              onFiltersChange({ ...filters, topic: event.target.value, page: 1 })
            }
          />
        </div>
      </div>
      <button
        className="evaluation-toggle"
        onClick={() => setShowEvaluations((current) => !current)}
      >
        {showEvaluations ? "Hide evaluations" : "Evaluation workspace"}
      </button>
      {showEvaluations && (
        <EvaluationPanel documents={documents} onError={onError} />
      )}

      <input
        ref={inputRef}
        hidden
        type="file"
        accept="application/pdf,.pdf"
        onChange={(event) => chooseFile(event.target.files?.[0])}
      />
      <button
        className="upload-button"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
      >
        {uploading ? (
          <LoaderCircle className="spin" size={18} />
        ) : (
          <Upload size={18} />
        )}
        {uploading ? "Uploading & indexing…" : "Upload PDF manual"}
      </button>

      <div className="document-list" aria-live="polite">
        {loading ? (
          <div className="panel-empty">
            <LoaderCircle className="spin" />
            Loading manuals…
          </div>
        ) : documents.length === 0 ? (
          <div className="panel-empty">
            <FileText />
            <strong>No manuals yet</strong>
            <span>Upload a text-based router PDF to begin.</span>
          </div>
        ) : (
          documents.map((document) => (
            <article
              className={`document-card ${expandedId === document.id ? "expanded" : ""}`}
              key={document.id}
            >
              <div className="document-icon">
                <FileText size={20} />
              </div>
              <div className="document-detail">
                <strong title={document.filename}>{document.filename}</strong>
                <div className={`status status-${document.status}`}>
                  <StatusIcon status={document.status} />
                  {statusLabels[document.status]}
                  {document.status === "indexed" &&
                    ` · ${document.page_count} pages`}
                </div>
                {document.error && <small>{document.error}</small>}
                <span>Version {document.version}</span>
                <span>
                  Knowledge: {document.enrichment_status}
                  {document.faq_count > 0 &&
                    ` · ${document.evaluation_pass_count}/${document.faq_count} FAQs passed`}
                </span>
              </div>
              <div className="document-actions">
                <button
                  title="Re-index"
                  aria-label={`Re-index ${document.filename}`}
                  disabled={busyId === document.id}
                  onClick={() => run(document.id, onReindex)}
                >
                  <RefreshCw
                    className={busyId === document.id ? "spin" : ""}
                    size={16}
                  />
                </button>
                <button
                  className="danger"
                  title="Delete"
                  aria-label={`Delete ${document.filename}`}
                  disabled={busyId === document.id}
                  onClick={() => run(document.id, onDelete)}
                >
                  <Trash2 size={16} />
                </button>
                <button
                  title="Review generated knowledge"
                  aria-label={`Review knowledge for ${document.filename}`}
                  onClick={() =>
                    setExpandedId((current) =>
                      current === document.id ? null : document.id,
                    )
                  }
                >
                  <ChevronDown
                    className={expandedId === document.id ? "rotate" : ""}
                    size={16}
                  />
                </button>
              </div>
              {expandedId === document.id && (
                <KnowledgePanel
                  documentId={document.id}
                  onChanged={onRefresh}
                  onError={onError}
                />
              )}
            </article>
          ))
        )}
      </div>

      <div className="document-pagination">
        <button
          disabled={pageInfo.page <= 1}
          onClick={() => onFiltersChange({ ...filters, page: pageInfo.page - 1 })}
        >
          Previous
        </button>
        <span>
          {pageInfo.page} / {pageInfo.total_pages}
        </span>
        <button
          disabled={pageInfo.page >= pageInfo.total_pages}
          onClick={() => onFiltersChange({ ...filters, page: pageInfo.page + 1 })}
        >
          Next
        </button>
      </div>

      <div className="privacy-note">
        <span className="privacy-dot" />
        PDFs stay local for indexing
      </div>
    </aside>
  );
}
