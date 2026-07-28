import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { DocumentPanel } from "./components/DocumentPanel";
import type { ChatMessage, DocumentRecord } from "./types";

const SESSION_KEY = "router-rag-session";

export default function App() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentPage, setDocumentPage] = useState({
    page: 1,
    total: 0,
    total_pages: 1,
  });
  const [documentFilters, setDocumentFilters] = useState<Record<string, string | number>>({
    page: 1,
    page_size: 25,
  });
  const [appliedDocumentFilters, setAppliedDocumentFilters] =
    useState(documentFilters);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showError = useCallback((caught: unknown) => {
    setError(caught instanceof Error ? caught.message : "Something went wrong.");
  }, []);

  const refreshDocuments = useCallback(async () => {
    const result = await api.listDocuments(appliedDocumentFilters);
    setDocuments(result.items);
    setDocumentPage({
      page: result.page,
      total: result.total,
      total_pages: result.total_pages,
    });
  }, [appliedDocumentFilters]);

  useEffect(() => {
    const timer = window.setTimeout(
      () => setAppliedDocumentFilters(documentFilters),
      300,
    );
    return () => window.clearTimeout(timer);
  }, [documentFilters]);

  const createSession = useCallback(async () => {
    const session = await api.createSession();
    localStorage.setItem(SESSION_KEY, session.id);
    setSessionId(session.id);
    setMessages([]);
    return session.id;
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        await refreshDocuments();
        const stored = localStorage.getItem(SESSION_KEY);
        if (stored) {
          try {
            setMessages(await api.getMessages(stored));
            setSessionId(stored);
          } catch {
            localStorage.removeItem(SESSION_KEY);
            await createSession();
          }
        } else {
          await createSession();
        }
      } catch (caught) {
        showError(caught);
      } finally {
        setLoadingDocuments(false);
      }
    })();
  }, [createSession, refreshDocuments]);

  const upload = async (file: File) => {
    setError(null);
    try {
      const document = await api.uploadDocument(file);
      await refreshDocuments();
    } catch (caught) {
      showError(caught);
    }
  };

  const remove = async (id: string) => {
    setError(null);
    try {
      await api.deleteDocument(id);
      setDocuments((current) => current.filter((item) => item.id !== id));
    } catch (caught) {
      showError(caught);
    }
  };

  const reindex = async (id: string) => {
    setError(null);
    try {
      const updated = await api.reindexDocument(id);
      setDocuments((current) =>
        current.map((item) => (item.id === id ? updated : item)),
      );
    } catch (caught) {
      showError(caught);
    }
  };

  const newChat = async () => {
    setError(null);
    try {
      if (sessionId) await api.deleteSession(sessionId).catch(() => undefined);
      await createSession();
    } catch (caught) {
      showError(caught);
    }
  };

  const ask = async (question: string) => {
    setError(null);
    setAsking(true);
    try {
      const activeSession = sessionId ?? (await createSession());
      const optimistic: ChatMessage = {
        id: `pending-${Date.now()}`,
        session_id: activeSession,
        role: "user",
        content: question,
        citations: [],
        created_at: new Date().toISOString(),
      };
      setMessages((current) => [...current, optimistic]);
      const result = await api.ask(activeSession, question);
      setMessages((current) => [
        ...current,
        {
          id: result.request_id,
          session_id: activeSession,
          role: "assistant",
          content: result.answer,
          rewritten_query: result.rewritten_query,
          grounded: result.grounded,
          citations: result.citations,
          suggested_questions: result.suggested_questions,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (caught) {
      showError(caught);
    } finally {
      setAsking(false);
    }
  };

  const indexedDocuments = documents.some(
    (document) => document.status === "indexed",
  );

  return (
    <div className="app-shell">
      <DocumentPanel
        documents={documents}
        loading={loadingDocuments}
        onUpload={upload}
        onDelete={remove}
        onReindex={reindex}
        onRefresh={refreshDocuments}
        onError={showError}
        pageInfo={documentPage}
        filters={documentFilters}
        onFiltersChange={setDocumentFilters}
      />
      <ChatPanel
        messages={messages}
        asking={asking}
        hasDocuments={indexedDocuments}
        onAsk={ask}
        onNewChat={newChat}
        onClearChat={newChat}
      />
      {error && (
        <div className="toast" role="alert">
          <span>{error}</span>
          <button aria-label="Dismiss error" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}
    </div>
  );
}
