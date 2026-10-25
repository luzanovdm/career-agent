import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { applyLocale } from "../src/app/i18n";
import { Exports, safeExportLink } from "../src/features/Exports";

async function testLabels() {
  await applyLocale({
    locale: "en",
    plural_categories: ["one", "other"],
    messages: {
      "exports.title": "Static exports",
      "exports.refreshHint":
        "After the agent regenerates an export, refresh this view to check its revision.",
      "exports.none": "No export information is available yet.",
      "exports.generated": "Generated",
      "exports.dateUnknown": "Generation time was not recorded.",
      "exports.unavailable":
        "Saved export unavailable; ask the agent to regenerate it.",
      "exports.download": "Download {name}",
      "exports.fileUnavailable": "{name} is unavailable for download.",
    },
  });
}

describe("read-only export discovery", () => {
  it("distinguishes stale, current and missing snapshots with manifest-owned downloads", async () => {
    await testLabels();
    const user = userEvent.setup();
    render(
      <Exports
        revision={22}
        exports={[
          {
            kind: "csv",
            revision: 2,
            status: "stale",
            generated_at: "2026-10-24T12:00:00Z",
            files: [
              {
                name: "Cases.csv",
                download_url: "/api/v1/exports/csv_opaque/files/0",
              },
            ],
          },
          {
            kind: "profile",
            revision: 22,
            status: "current",
            generated_at: null,
            files: [
              {
                name: "Profile.md",
                download_url: "/api/v1/exports/profile_opaque/files/0",
              },
            ],
          },
          { kind: "xlsx", revision: null, status: "missing", files: [] },
        ]}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Static exports are out of date" }),
    );
    expect(screen.getByText("Out of date · revision 2")).toBeVisible();
    expect(screen.getByText("Current · revision 22")).toBeVisible();
    expect(screen.getByText("Not generated")).toBeVisible();
    expect(
      screen.getByText(/The live interface reads revision 22/),
    ).toBeVisible();
    expect(
      screen.getByText(/refresh this view to check its revision/),
    ).toBeVisible();
    expect(screen.getByText("Generation time was not recorded.")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Download Cases.csv" }),
    ).toHaveAttribute("href", "/api/v1/exports/csv_opaque/files/0");
    expect(
      screen.getByRole("link", { name: "Download Profile.md" }),
    ).toHaveAttribute("download");
    expect(document.querySelector("time")).toHaveAttribute(
      "dateTime",
      "2026-10-24T12:00:00Z",
    );
    expect(screen.queryByRole("button", { name: /regenerate/i })).toBeNull();
  });

  it("never turns external or arbitrary local paths into export downloads", async () => {
    await testLabels();
    const user = userEvent.setup();
    for (const value of [
      "https://external.example/data.csv",
      "//external.example/data.csv",
      "javascript:alert(1)",
      "/api/v1/exports/../../private/files/0",
      "/api/v1/exports/opaque/files/0?path=/private",
      "/api/v1/exports/opaque/files/%30",
      "/Data/private.csv",
    ])
      expect(safeExportLink(value)).toBeUndefined();
    expect(safeExportLink("/api/v1/exports/opaque_1-abc/files/0")).toBe(
      "/api/v1/exports/opaque_1-abc/files/0",
    );
    render(
      <Exports
        revision={22}
        exports={[
          {
            kind: "csv",
            revision: 22,
            status: "current",
            issue: "MISSING_FILE",
            files: [
              {
                name: "Unsafe.csv",
                download_url: "https://external.example/unsafe.csv",
              },
            ],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Static exports" }));
    expect(screen.queryByRole("link")).toBeNull();
    expect(
      screen.getByText("Unsafe.csv is unavailable for download."),
    ).toBeVisible();
    expect(screen.getByText(/Saved export unavailable/)).toBeVisible();
  });

  it("keeps the export entry discoverable before any export exists", async () => {
    await testLabels();
    const user = userEvent.setup();
    render(<Exports revision={0} exports={[]} />);
    await user.click(screen.getByRole("button", { name: "Static exports" }));
    expect(
      screen.getByText("No export information is available yet."),
    ).toBeVisible();
  });
});
