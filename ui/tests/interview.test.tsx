import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Interview, type InterviewItem } from "../src/features/Interview";
function turn(kind: InterviewItem["kind"], text: string): InterviewItem {
  return {
    slot: "interview",
    artifact_id: "artifact_demo",
    kind,
    text,
    status: kind === "question" ? "hypothesis" : "outline",
    sources: [],
    terms: [],
  };
}
describe("explicit saved interview dialogue", () => {
  it("renders actual contract Q/A items and links only their saved readable term references", () => {
    const items = [
      turn("question", "How would you explain the concept?"),
      turn("answer", "I would use the documented example term."),
      turn("question", "What would you ask the team?"),
      turn("answer", "I would ask about the supported workflow."),
    ];
    items[1].terms = [
      {
        label: "example term",
        url: "https://workflow.example/concept",
        source_id: "source_term",
        available: true,
        limitation: null,
      },
    ];
    items[1].sources = [
      {
        id: "source_term",
        locator: "https://workflow.example/concept",
        observed_at: "2026-10-24T00:00:00Z",
        readable: true,
        available: true,
      },
    ];
    render(
      <Interview
        detail={{ interview: items }}
        onMaterials={() => {}}
        materialLanguage="en"
      />,
    );
    const sequence = screen.getByRole("list", {
      name: "Saved interview sequence",
    });
    expect(within(sequence).getAllByRole("listitem")).toHaveLength(4);
    expect(document.querySelectorAll(".dialogue .answer")).toHaveLength(2);
    expect(document.querySelectorAll(".dialogue .question")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "example term" })).toHaveAttribute(
      "href",
      "https://workflow.example/concept",
    );
    expect(screen.getByRole("link", { name: "example term" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(document.querySelector("p[lang='en']")).toBeTruthy();
  });
  it("keeps old text as one document and never infers speakers from role headings or array position", () => {
    const text =
      "INTERVIEWER\nSaved question\nAPPLICANT OUTLINE\nSaved answer outline <img src=x onerror=alert(1)>";
    render(
      <Interview
        detail={{
          interview: [{ slot: "interview", artifact_id: "artifact_doc", text }],
        }}
        onMaterials={() => {}}
      />,
    );
    expect(document.querySelectorAll(".dialogue > li")).toHaveLength(1);
    expect(document.querySelectorAll(".dialogue .answer")).toHaveLength(0);
    expect(document.querySelector(".dialogue > li p")?.textContent).toBe(text);
    expect(document.querySelector("img")).toBeNull();
  });
  it("shows unavailable references honestly without clickable invented links", () => {
    const item = turn("answer", "Saved outline with a missing term.");
    item.terms = [
      {
        label: "missing term",
        url: "https://workflow.example/unknown",
        source_id: "source_missing",
        available: false,
        limitation: "Missing",
      },
    ];
    render(<Interview detail={{ interview: [item] }} onMaterials={() => {}} />);
    expect(screen.getByText(/Reference unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("has honest empty and file-only states without starting coaching or creating content", async () => {
    const user = userEvent.setup();
    const onMaterials = vi.fn();
    const view = render(
      <Interview detail={{ interview: [] }} onMaterials={onMaterials} />,
    );
    expect(
      screen.getByRole("heading", { name: "No saved preparation yet" }),
    ).toBeInTheDocument();
    expect(onMaterials).not.toHaveBeenCalled();
    view.rerender(
      <Interview
        detail={{
          interview: [
            {
              slot: "interview",
              artifact_id: "artifact_file",
              text: null,
              kind: "file",
            },
          ],
        }}
        onMaterials={onMaterials}
      />,
    );
    expect(
      screen.getByText(/Preparation is saved as a file/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Materials" }));
    expect(onMaterials).toHaveBeenCalledOnce();
  });
});
