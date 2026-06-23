import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { api } from "../api";
import { EvaluationPanel } from "./EvaluationPanel";

describe("EvaluationPanel", () => {
  it("creates a dataset and starts an evaluation run", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue({
      items: [],
      page: 1,
      page_size: 100,
      total: 0,
      total_pages: 1,
    });
    vi.spyOn(api, "listDatasets")
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "dataset-1",
          name: "Pilot",
          description: null,
          question_count: 0,
        },
      ]);
    vi.spyOn(api, "createDataset").mockResolvedValue({
      id: "dataset-1",
      name: "Pilot",
      description: null,
    });
    vi.spyOn(api, "getDataset").mockResolvedValue({
      id: "dataset-1",
      name: "Pilot",
      description: null,
      questions: [],
    });
    vi.spyOn(api, "createEvaluationRun").mockResolvedValue({
      id: "run-1",
      dataset_id: "dataset-1",
      status: "queued",
      progress: 0,
      total_questions: 0,
      completed_questions: 0,
      config: {},
      document_versions: {},
      metrics: {},
      passed: null,
      error: null,
    });

    render(<EvaluationPanel documents={[]} onError={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Dataset name"), {
      target: { value: "Pilot" },
    });
    fireEvent.click(screen.getByText("Create"));

    expect(await screen.findByText("Run evaluation")).toBeTruthy();
    fireEvent.click(screen.getByText("Run evaluation"));
    await waitFor(() =>
      expect(api.createEvaluationRun).toHaveBeenCalledWith("dataset-1"),
    );
  });
});
