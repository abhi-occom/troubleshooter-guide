import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { api } from "../api";
import type { DocumentKnowledge } from "../types";
import { KnowledgePanel } from "./KnowledgePanel";

const knowledge: DocumentKnowledge = {
  document: {
    id: "doc-1",
    filename: "router.pdf",
    sha256: "hash",
    version: 1,
    status: "indexed",
    page_count: 2,
    chunk_count: 4,
    error: null,
    enrichment_status: "ready",
    enrichment_error: null,
    profile_status: "ready",
    faq_count: 1,
    evaluation_pass_count: 1,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
  profile: {
    document_id: "doc-1",
    router_name: "HOME MESH PRO",
    model: "Wi-Fi 7",
    product_id: "171118",
    supported_configuration: "Two units",
    features: ["Mesh"],
    topics: ["reset"],
    identifier_aliases: [],
    provenance: {
      router_name: {
        chunk_id: "doc-1:1:0",
        page: 1,
        excerpt: "HOME MESH PRO",
      },
    },
    extracted_values: {},
    manual_fields: [],
    status: "ready",
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
  faqs: [
    {
      id: "faq-1",
      document_id: "doc-1",
      question: "How do I reset HOME MESH PRO?",
      expected_topic: "reset",
      source_chunk_id: "doc-1:2:0",
      source_page: 2,
      source_excerpt: "Hold reset for ten seconds.",
      approved: true,
      alias_active: true,
      passed: true,
      best_distance: 0.12,
      retrieved_pages: [2],
      expected_source_found: true,
      evaluated_at: "2026-01-01",
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
    },
  ],
  job: {
    id: "job-1",
    document_id: "doc-1",
    status: "completed",
    progress: 100,
    attempts: 1,
    max_attempts: 3,
    error: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    started_at: "2026-01-01",
    completed_at: "2026-01-01",
  },
};

describe("KnowledgePanel", () => {
  it("shows extracted profile, FAQ evaluation, and regenerates", async () => {
    vi.spyOn(api, "getKnowledge").mockResolvedValue(knowledge);
    vi.spyOn(api, "enrichDocument").mockResolvedValue({});
    const onChanged = vi.fn().mockResolvedValue(undefined);

    render(
      <KnowledgePanel
        documentId="doc-1"
        onChanged={onChanged}
        onError={vi.fn()}
      />,
    );

    expect(await screen.findByDisplayValue("HOME MESH PRO")).toBeTruthy();
    expect(screen.getByText("How do I reset HOME MESH PRO?")).toBeTruthy();
    fireEvent.click(screen.getByText("Regenerate"));

    await waitFor(() => {
      expect(api.enrichDocument).toHaveBeenCalledWith("doc-1");
      expect(onChanged).toHaveBeenCalled();
    });
  });
});
