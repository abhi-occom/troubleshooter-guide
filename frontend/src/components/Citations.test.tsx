import { render, screen } from "@testing-library/react";
import { Citations } from "./Citations";

describe("Citations", () => {
  it("renders document and page provenance", () => {
    render(
      <Citations
        citations={[
          {
            document_id: "doc-1",
            document: "mesh-router.pdf",
            page: 7,
            excerpt: "Hold reset for ten seconds.",
            distance: 0.2,
          },
        ]}
      />,
    );

    expect(screen.getByText("mesh-router.pdf")).toBeTruthy();
    expect(screen.getByText("Page 7")).toBeTruthy();
    expect(screen.getByText("Hold reset for ten seconds.")).toBeTruthy();
  });
});
