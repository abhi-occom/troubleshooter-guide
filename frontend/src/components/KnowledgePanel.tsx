import {
  CheckCircle2,
  ChevronDown,
  CircleX,
  LoaderCircle,
  RefreshCw,
  Save,
  Sparkles,
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import type { DocumentKnowledge, RouterProfile } from "../types";

interface Props {
  documentId: string;
  onChanged: () => Promise<void>;
  onError: (error: unknown) => void;
}

type ProfileForm = Pick<
  RouterProfile,
  | "router_name"
  | "model"
  | "product_id"
  | "supported_configuration"
> & {
  features: string;
  topics: string;
  identifier_aliases: string;
};

function formFromProfile(profile: RouterProfile): ProfileForm {
  return {
    router_name: profile.router_name,
    model: profile.model,
    product_id: profile.product_id,
    supported_configuration: profile.supported_configuration,
    features: profile.features.join(", "),
    topics: profile.topics.join(", "),
    identifier_aliases: (profile.identifier_aliases ?? []).join(", "),
  };
}

export function KnowledgePanel({ documentId, onChanged, onError }: Props) {
  const [knowledge, setKnowledge] = useState<DocumentKnowledge | null>(null);
  const [form, setForm] = useState<ProfileForm | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const next = await api.getKnowledge(documentId);
    setKnowledge(next);
    if (next.profile) setForm(formFromProfile(next.profile));
    return next;
  };

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const next = await api.getKnowledge(documentId);
        if (!active) return;
        setKnowledge(next);
        if (next.profile) {
          setForm((current) => current ?? formFromProfile(next.profile!));
        }
        if (next.job && ["queued", "running"].includes(next.job.status)) {
          await onChanged();
        }
      } catch (error) {
        if (active) onError(error);
      }
    };
    void poll();
    const timer = window.setInterval(poll, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [documentId, onError]);

  const saveProfile = async (event: FormEvent) => {
    event.preventDefault();
    if (!form) return;
    setBusy(true);
    try {
      await api.updateProfile(documentId, {
        router_name: form.router_name,
        model: form.model,
        product_id: form.product_id,
        supported_configuration: form.supported_configuration,
        features: form.features
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        topics: form.topics
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        identifier_aliases: form.identifier_aliases
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      });
      await load();
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async () => {
    setBusy(true);
    try {
      await api.enrichDocument(documentId);
      await load();
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  };

  const toggleFaq = async (
    faqId: string,
    approved: boolean,
    aliasActive: boolean,
  ) => {
    setBusy(true);
    try {
      await api.updateFaq(documentId, faqId, approved, aliasActive);
      await load();
      await onChanged();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  };

  if (!knowledge) {
    return (
      <div className="knowledge-loading">
        <LoaderCircle className="spin" size={16} />
        Loading generated knowledge…
      </div>
    );
  }

  return (
    <div className="knowledge-panel">
      <div className="knowledge-status">
        <div>
          <strong>Automatic knowledge</strong>
          <span>
            {knowledge.job
              ? `${knowledge.job.status} · ${knowledge.job.progress}%`
              : "Not generated"}
          </span>
        </div>
        <button disabled={busy} onClick={regenerate}>
          <RefreshCw className={busy ? "spin" : ""} size={14} />
          Regenerate
        </button>
      </div>

      {knowledge.job?.error && (
        <div className="knowledge-error">{knowledge.job.error}</div>
      )}

      {form && knowledge.profile ? (
        <form className="profile-form" onSubmit={saveProfile}>
          <p className="knowledge-label">Router profile</p>
          {[
            ["router_name", "Router name"],
            ["model", "Model"],
            ["product_id", "Product ID"],
            ["supported_configuration", "Supported configuration"],
            ["features", "Features (comma separated)"],
            ["topics", "Topics (comma separated)"],
            ["identifier_aliases", "Model aliases (comma separated)"],
          ].map(([field, label]) => (
            <label key={field}>
              <span>
                {label}
                {knowledge.profile?.manual_fields.includes(field) && (
                  <b>Edited</b>
                )}
              </span>
              <input
                value={String(form[field as keyof ProfileForm] ?? "")}
                onChange={(event) =>
                  setForm((current) =>
                    current
                      ? { ...current, [field]: event.target.value }
                      : current,
                  )
                }
              />
              {knowledge.profile?.provenance[field] && (
                <small>
                  Page {knowledge.profile.provenance[field].page}:{" "}
                  {knowledge.profile.provenance[field].excerpt}
                </small>
              )}
            </label>
          ))}
          <button className="knowledge-primary" disabled={busy} type="submit">
            <Save size={14} />
            Save corrections
          </button>
        </form>
      ) : (
        <div className="knowledge-empty">
          <Sparkles size={16} />
          Profile generation is pending.
        </div>
      )}

      <div className="faq-list">
        <p className="knowledge-label">
          Generated FAQs <span>{knowledge.faqs.length}</span>
        </p>
        {knowledge.faqs.map((faq) => (
          <details key={faq.id}>
            <summary>
              {faq.passed ? (
                <CheckCircle2 className="faq-pass" size={15} />
              ) : (
                <CircleX className="faq-fail" size={15} />
              )}
              <span>{faq.question}</span>
              <ChevronDown size={14} />
            </summary>
            <div className="faq-detail">
              <p>
                Topic: {faq.expected_topic || "Unspecified"} · Source page{" "}
                {faq.source_page}
              </p>
              <blockquote>{faq.source_excerpt}</blockquote>
              <p>
                Evaluation: {faq.passed ? "Passed" : "Failed"} · Best distance:{" "}
                {faq.best_distance?.toFixed(3) ?? "n/a"}
              </p>
              <label className="faq-toggle">
                <input
                  type="checkbox"
                  checked={faq.approved && faq.alias_active}
                  disabled={busy}
                  onChange={(event) =>
                    toggleFaq(
                      faq.id,
                      event.target.checked,
                      event.target.checked,
                    )
                  }
                />
                Use as retrieval hint
              </label>
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
