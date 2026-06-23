import type {
  AskResult,
  ChatMessage,
  DocumentKnowledge,
  DocumentPage,
  DocumentRecord,
  GeneratedFaq,
  EvaluationDataset,
  EvaluationQuestion,
  EvaluationRun,
  RouterProfile,
  Session,
} from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : body.detail?.message ?? message;
    } catch {
      // Keep the status-based message for non-JSON errors.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  listDocuments: (params: Record<string, string | number | undefined> = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<DocumentPage>(`/api/documents?${query.toString()}`);
  },

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentRecord>("/api/documents", {
      method: "POST",
      body: form,
    });
  },

  reindexDocument: (id: string) =>
    request<DocumentRecord>(`/api/documents/${id}/reindex`, {
      method: "POST",
    }),

  deleteDocument: (id: string) =>
    request<void>(`/api/documents/${id}`, { method: "DELETE" }),

  getKnowledge: (id: string) =>
    request<DocumentKnowledge>(`/api/documents/${id}/knowledge`),

  updateProfile: (
    id: string,
    profile: Partial<
      Pick<
        RouterProfile,
        | "router_name"
        | "model"
        | "product_id"
        | "supported_configuration"
        | "features"
        | "topics"
        | "identifier_aliases"
      >
    >,
  ) =>
    request<RouterProfile>(`/api/documents/${id}/profile`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    }),

  enrichDocument: (id: string) =>
    request(`/api/documents/${id}/enrich`, { method: "POST" }),

  updateFaq: (
    documentId: string,
    faqId: string,
    approved: boolean,
    aliasActive: boolean,
  ) =>
    request<GeneratedFaq>(
      `/api/documents/${documentId}/faqs/${faqId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved,
          alias_active: aliasActive,
        }),
      },
    ),

  createSession: () =>
    request<Session>("/api/chat/sessions", { method: "POST" }),

  getMessages: (sessionId: string) =>
    request<ChatMessage[]>(`/api/chat/sessions/${sessionId}/messages`),

  deleteSession: (sessionId: string) =>
    request<void>(`/api/chat/sessions/${sessionId}`, { method: "DELETE" }),

  ask: (sessionId: string, question: string) =>
    request<AskResult>("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, question }),
    }),

  listDatasets: () =>
    request<EvaluationDataset[]>("/api/evaluation/datasets"),
  createDataset: (name: string, description = "") =>
    request<EvaluationDataset>("/api/evaluation/datasets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    }),
  getDataset: (id: string) =>
    request<EvaluationDataset>(`/api/evaluation/datasets/${id}`),
  updateDataset: (id: string, changes: Partial<EvaluationDataset>) =>
    request<EvaluationDataset>(`/api/evaluation/datasets/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
  deleteDataset: (id: string) =>
    request<void>(`/api/evaluation/datasets/${id}`, { method: "DELETE" }),
  addEvaluationQuestion: (
    datasetId: string,
    question: Omit<EvaluationQuestion, "id" | "dataset_id">,
  ) =>
    request<EvaluationQuestion>(
      `/api/evaluation/datasets/${datasetId}/questions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(question),
      },
    ),
  updateEvaluationQuestion: (
    questionId: string,
    changes: Partial<EvaluationQuestion>,
  ) =>
    request<EvaluationQuestion>(`/api/evaluation/questions/${questionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
  deleteEvaluationQuestion: (questionId: string) =>
    request<void>(`/api/evaluation/questions/${questionId}`, {
      method: "DELETE",
    }),
  importEvaluationCsv: (datasetId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ imported: number }>(
      `/api/evaluation/datasets/${datasetId}/import`,
      { method: "POST", body: form },
    );
  },
  createEvaluationRun: (datasetId: string) =>
    request<EvaluationRun>(`/api/evaluation/datasets/${datasetId}/runs`, {
      method: "POST",
    }),
  getEvaluationRun: (runId: string) =>
    request<EvaluationRun>(`/api/evaluation/runs/${runId}`),
  getEvaluationResults: (runId: string) =>
    request<Record<string, unknown>[]>(
      `/api/evaluation/runs/${runId}/results`,
    ),
};
