import {
  Bot,
  LoaderCircle,
  MessageSquarePlus,
  Send,
  Sparkles,
  Trash2,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";
import { Citations } from "./Citations";

interface Props {
  messages: ChatMessage[];
  asking: boolean;
  hasDocuments: boolean;
  onAsk: (question: string) => Promise<void>;
  onNewChat: () => Promise<void>;
  onClearChat: () => Promise<void>;
}

export function ChatPanel({
  messages,
  asking,
  hasDocuments,
  onAsk,
  onNewChat,
  onClearChat,
}: Props) {
  const [question, setQuestion] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof endRef.current?.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, asking]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = question.trim();
    if (!value || asking) return;
    setQuestion("");
    await onAsk(value);
  };

  return (
    <main className="chat-panel">
      <header className="chat-header">
        <div>
          <p className="eyebrow">Support workspace</p>
          <h1>Ask your router manuals</h1>
        </div>
        <div className="header-actions">
          <button className="secondary-button" onClick={onNewChat}>
            <MessageSquarePlus size={17} />
            New chat
          </button>
          <button
            className="icon-button"
            aria-label="Clear chat"
            title="Clear chat"
            disabled={!messages.length}
            onClick={onClearChat}
          >
            <Trash2 size={17} />
          </button>
        </div>
      </header>

      <section className="messages" aria-live="polite">
        {messages.length === 0 ? (
          <div className="welcome">
            <div className="welcome-icon">
              <Sparkles />
            </div>
            <p className="eyebrow">Documentation, made useful</p>
            <h2>What can I help you troubleshoot?</h2>
            <p>
              Ask a direct question, then keep the conversation going with
              follow-ups like “what if that doesn’t work?”
            </p>
            <div className="suggestions">
              <button
                disabled={!hasDocuments}
                onClick={() => setQuestion("How do I reset the router?")}
              >
                How do I reset the router?
              </button>
              <button
                disabled={!hasDocuments}
                onClick={() =>
                  setQuestion("What does a red status light mean?")
                }
              >
                What does a red status light mean?
              </button>
            </div>
            {!hasDocuments && (
              <span className="empty-hint">
                Upload a router manual to start asking questions.
              </span>
            )}
          </div>
        ) : (
          messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <div className="avatar">
                {message.role === "assistant" ? <Bot size={18} /> : "You"}
              </div>
              <div className="message-body">
                <div className="message-meta">
                  <strong>
                    {message.role === "assistant"
                      ? "Router Guide AI"
                      : "You"}
                  </strong>
                  {message.role === "assistant" &&
                    message.grounded === false && (
                      <span className="not-found">Not found in manuals</span>
                    )}
                </div>
                <p>{message.content}</p>
                {message.rewritten_query && (
                  <small className="rewritten">
                    Searched for: {message.rewritten_query}
                  </small>
                )}
                <Citations citations={message.citations} />
              </div>
            </article>
          ))
        )}
        {asking && (
          <article className="message assistant">
            <div className="avatar">
              <Bot size={18} />
            </div>
            <div className="thinking">
              <LoaderCircle className="spin" size={17} />
              Checking the manuals and conversation context…
            </div>
          </article>
        )}
        <div ref={endRef} />
      </section>

      <form className="composer" onSubmit={submit}>
        <div className="composer-box">
          <textarea
            aria-label="Ask a router question"
            placeholder={
              hasDocuments
                ? "Ask a troubleshooting question…"
                : "Upload a manual before asking a question"
            }
            value={question}
            disabled={!hasDocuments || asking}
            rows={1}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button
            aria-label="Send question"
            disabled={!hasDocuments || asking || !question.trim()}
            type="submit"
          >
            <Send size={18} />
          </button>
        </div>
        <p>
          Answers are generated only from indexed manuals. Always verify safety
          instructions before servicing equipment.
        </p>
      </form>
    </main>
  );
}
