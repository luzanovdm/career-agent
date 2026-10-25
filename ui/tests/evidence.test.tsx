import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Api } from "../src/api/client";
import { EvidenceBank } from "../src/features/EvidenceBank";
import { SourceEvidence } from "../src/features/SourceEvidence";
import { Profile } from "../src/features/Profile";
import { t } from "../src/app/i18n";
import type {
  EvidenceAnswer,
  EvidenceContext,
} from "../src/features/evidenceTypes";
import { context, receipt } from "./fixtures";
const pending: EvidenceAnswer = {
  id: "answer-open",
  meaning: "availability.start",
  scope: { track_id: "track-product" },
  units: {},
  disposition: "pending",
  value: null,
  evidence: "Open fictional question: when can the candidate start?",
  response_state: "pending",
  reusable_here: false,
  value_reusable_here: false,
  scope_unresolved: false,
  valid_now: true,
  valid_from: null,
  valid_until: null,
};
function page(next = false, revision = 1): EvidenceContext {
  return {
    ...context,
    revision,
    tracks: context.tracks,
    next_cursor: next ? null : "next-fictional-page",
    partial: !next,
    pagination: {
      claims: {
        total: 2,
        offset: next ? 1 : 0,
        returned: 1,
        remaining: next ? 0 : 1,
        omitted_by_scope: 0,
      },
      answers: {
        total: 4,
        offset: next ? 2 : 0,
        returned: 2,
        remaining: next ? 0 : 2,
        omitted_by_scope: 0,
      },
      sources: {
        total: 1,
        offset: 0,
        returned: 1,
        remaining: 0,
        omitted_by_scope: 0,
      },
    },
    evidence: {
      claims: [
        {
          id: next ? "claim-b" : "claim-a",
          assertion: next
            ? "Led a supported service handover."
            : "Reduced processing time by 25%.",
          meaning: next
            ? "Personal responsibility was the handover."
            : "Personal contribution with exact percentage.",
          confirmation: "confirmed",
          disclosure: "allowed",
          contradicted: false,
          source_ids: ["source-one"],
        },
      ],
      answers: next
        ? [
            {
              ...pending,
              id: "timeline",
              meaning: "profile.timeline",
              disposition: "answered",
              response_state: "provided",
              value: [
                {
                  company: "Aurora Example",
                  role: "Process analyst",
                  start: "2021",
                  end: "2024",
                },
              ],
            },
            {
              ...pending,
              id: "resumes",
              meaning: "profile.selected_resumes",
              disposition: "answered",
              response_state: "provided",
              value: [
                {
                  artifact_id: "artifact-original",
                  language: "en",
                  sha256: "a".repeat(64),
                },
              ],
            },
          ]
        : [
            pending,
            {
              ...pending,
              id: "answer-unknown",
              meaning: "compensation.external",
              disposition: "unknown",
              response_state: "provided",
              evidence: "The fictional user explicitly does not know.",
              units: { currency: "PLN", period: "month" },
            },
          ],
      sources: [
        {
          id: "source-one",
          locator: "https://aurora.example/source",
          excerpt: "Short excerpt",
          observed_at: "2026-10-24T00:00:00Z",
          readable: true,
          excerpt_truncated: true,
        },
      ],
    },
  };
}
describe("bounded readable career evidence", () => {
  it("consumes continuation for claims, scoped pending/unknown answers, timeline and exact resume downloads", async () => {
    const user = userEvent.setup(),
      api = new Api();
    const request = vi
      .spyOn(api, "request")
      .mockImplementation(async (path) =>
        path.includes("cursor=") ? page(true) : page(),
      );
    const command = vi.spyOn(api, "command");
    render(
      <EvidenceBank
        api={api}
        workspaceId={context.workspace_id}
        revision={1}
      />,
    );
    expect(
      await screen.findByRole("heading", {
        name: "Reduced processing time by 25%.",
      }),
    ).toBeVisible();
    await user.click(screen.getByRole("tab", { name: t("evidence.answers") }));
    expect(screen.getByText(t("evidence.disposition.pending"))).toBeVisible();
    expect(screen.getByText(t("evidence.disposition.unknown"))).toBeVisible();
    expect(screen.getByText(t("evidence.pendingHint"))).toBeVisible();
    expect(screen.getByText("PLN")).toBeVisible();
    await user.click(screen.getByRole("button", { name: t("evidence.more") }));
    expect(
      await screen.findByRole("heading", { name: t("evidence.timeline") }),
    ).toBeVisible();
    expect(screen.getByText("Process analyst")).toBeVisible();
    expect(screen.getByText("2021")).toBeVisible();
    expect(
      screen.getByRole("link", { name: t("evidence.downloadSaved") }),
    ).toHaveAttribute("href", "/api/v1/artifacts/artifact-original/download");
    await user.click(screen.getByRole("tab", { name: t("evidence.claims") }));
    expect(screen.getByText("Led a supported service handover.")).toBeVisible();
    expect(request.mock.calls[1][0]).toContain("cursor=next-fictional-page");
    expect(
      screen.queryByRole("button", { name: t("evidence.more") }),
    ).not.toBeInTheDocument();
    expect(command).not.toHaveBeenCalled();
  });
  it("loads complete source evidence only when opened", async () => {
    const user = userEvent.setup(),
      api = new Api();
    const request = vi.spyOn(api, "request").mockResolvedValue({
      ...context,
      source: {
        id: "source-one",
        locator: "https://aurora.example/source",
        excerpt: "Full saved evidence and exact observation.",
        observed_at: "2026-10-24T00:00:00Z",
        readable: true,
      },
    });
    render(
      <SourceEvidence
        api={api}
        sourceId="source-one"
        workspaceId={context.workspace_id}
        revision={1}
      />,
    );
    expect(request).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: t("evidence.openSource") }),
    );
    expect(
      await screen.findByText("Full saved evidence and exact observation."),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "https://aurora.example/source" }),
    ).toHaveAttribute("rel", "noopener noreferrer");
    expect(request.mock.calls[0][0]).toBe(
      "/api/v1/context?source_id=source-one",
    );
  });
  it("refuses source content from another workspace", async () => {
    const user = userEvent.setup(),
      api = new Api();
    vi.spyOn(api, "request").mockResolvedValue({
      ...context,
      workspace_id: "other-workspace",
      source: {
        id: "source-one",
        locator: "https://other.example/source",
        excerpt: "Wrong workspace content must stay hidden.",
        observed_at: "2026-10-24T00:00:00Z",
        readable: true,
      },
    });
    render(
      <SourceEvidence
        api={api}
        sourceId="source-one"
        workspaceId={context.workspace_id}
        revision={1}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: t("evidence.openSource") }),
    );
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(
      screen.queryByText("Wrong workspace content must stay hidden."),
    ).not.toBeInTheDocument();
  });
  it("uses case scope and rejects stale continuation without appending a different revision", async () => {
    const user = userEvent.setup(),
      api = new Api();
    const request = vi
      .spyOn(api, "request")
      .mockImplementation(async (path) =>
        path.includes("cursor=") ? page(true, 2) : page(),
      );
    render(
      <EvidenceBank
        api={api}
        workspaceId={context.workspace_id}
        revision={1}
        caseId="case-aurora"
      />,
    );
    await screen.findByText("Reduced processing time by 25%.");
    expect(request.mock.calls[0][0]).toContain("task=packets");
    expect(request.mock.calls[0][0]).toContain("case_id=case-aurora");
    await user.click(screen.getByRole("button", { name: t("evidence.more") }));
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(
      screen.queryByText("Led a supported service handover."),
    ).not.toBeInTheDocument();
  });
  it("drops a late earlier generation when the live revision changes", async () => {
    const api = new Api();
    let resolveOld!: (value: EvidenceContext) => void;
    vi.spyOn(api, "request")
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve as (value: EvidenceContext) => void;
          }),
      )
      .mockResolvedValue(page(true, 2));
    const view = render(
      <EvidenceBank
        api={api}
        workspaceId={context.workspace_id}
        revision={1}
      />,
    );
    view.rerender(
      <EvidenceBank
        api={api}
        workspaceId={context.workspace_id}
        revision={2}
      />,
    );
    expect(
      await screen.findByText("Led a supported service handover."),
    ).toBeVisible();
    await act(async () => {
      resolveOld(page());
      await Promise.resolve();
    });
    await waitFor(() =>
      expect(
        screen.queryByText("Reduced processing time by 25%."),
      ).not.toBeInTheDocument(),
    );
  });
  it("whitelists existing track command fields from an actual API-shaped track", async () => {
    const user = userEvent.setup(),
      api = new Api();
    vi.spyOn(api, "request").mockResolvedValue(page());
    const command = vi.spyOn(api, "command").mockResolvedValue(receipt);
    const track = {
      ...context.tracks[0],
      version: 9,
      claim_ids: ["claim-a"],
      policies: { geography: { state: "known", value: "Example city" } },
    };
    render(
      <Profile
        context={{ ...context, tracks: [track] }}
        api={api}
        onDirty={() => {}}
        refresh={() => {}}
        onAgent={() => {}}
      />,
    );
    const section = screen
      .getByRole("heading", { name: track.name })
      .closest("section")!;
    await user.click(
      within(section).getByRole("button", { name: t("common.edit") }),
    );
    const input = within(section).getByRole("textbox", {
      name: t("profile.trackName"),
    });
    await user.clear(input);
    await user.type(input, "Updated supported direction");
    await user.click(
      within(section).getByRole("button", { name: t("common.save") }),
    );
    await waitFor(() => expect(command).toHaveBeenCalled());
    expect(command.mock.calls[0][0]).toBe("track.save");
    expect(command.mock.calls[0][1]).toEqual({
      id: track.id,
      name: "Updated supported direction",
      positioning: track.positioning,
      selected: track.selected,
      language: track.language,
      policies: track.policies,
      claim_ids: ["claim-a"],
    });
    expect(command.mock.calls[0][1]).not.toHaveProperty("version");
  });
});
