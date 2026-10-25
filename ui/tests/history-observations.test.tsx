import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Api } from "../src/api/client";
import { t } from "../src/app/i18n";
import {
  RetainedHistory,
  type RetainedHistoryPage,
  type RetainedObservation,
} from "../src/features/RetainedHistory";
const observation: RetainedObservation = {
  format: "career-agent.history-observation/1",
  id: "observation-fictional-one",
  original_status: "uncertain",
  event_kind: "initial_application",
  evidence_level: "user_reported",
  employer: "Northstar Example",
  role: "Analyst",
  role_url: "https://northstar.example/roles/42",
  date: {
    text: "around March 2020",
    precision: "approximate",
    occurred_at: null,
  },
  channel: "email",
  evidence: "Fictional user report; transmission unverified.",
  source: {
    record_history_id: 3,
    sha256: "a".repeat(64),
    locator: "Fictional user list",
    kind: "user_list",
  },
  historical_opportunity_reference: "old-role-reference",
  provider_message_id: null,
  provider_thread_id: null,
  case_id: null,
  scope: "unlinked",
  canonical_activity_created: false,
};
const page: RetainedHistoryPage = {
  workspace_id: "fictional",
  revision: 22,
  items: [observation],
  total: 2,
  next_cursor: "second-page",
  pending_projection: 0,
  projection_current: true,
};
describe("read-only unlinked history", () => {
  it("reads all pages without guessing role links, exact dates or canonical sends", async () => {
    const api = new Api();
    const user = userEvent.setup();
    vi.spyOn(api, "request")
      .mockResolvedValueOnce(page)
      .mockResolvedValueOnce({
        ...page,
        next_cursor: null,
        items: [
          {
            ...observation,
            id: "observation-two",
            employer: "Harbor Example",
            original_status: "bounced",
          },
        ],
      });
    vi.spyOn(api, "command");
    render(<RetainedHistory api={api} workspaceId="fictional" revision={22} />);
    expect(
      await screen.findByRole("heading", {
        name: "Northstar Example · Analyst",
      }),
    ).toBeVisible();
    expect(
      screen.getByText("around March 2020", { exact: false }),
    ).toBeVisible();
    expect(screen.getByText(t("history.unlinked"))).toBeVisible();
    expect(
      screen.getByText(
        t("history.originalStatus", { status: t("history.status.uncertain") }),
      ),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: t("history.moreRetained") }),
    );
    expect(
      await screen.findByRole("heading", { name: "Harbor Example · Analyst" }),
    ).toBeVisible();
    expect(
      screen.getByText(t("history.retainedProgress", { shown: 2, total: 2 })),
    ).toBeVisible();
    expect(api.request).toHaveBeenLastCalledWith(
      "/api/v1/history/observations?limit=25&cursor=second-page",
      { signal: undefined },
    );
    expect(api.command).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain(
      '"canonical_activity_created"',
    );
  });
  it("shows pending projection honestly rather than claiming absent historical data", async () => {
    const api = new Api();
    vi.spyOn(api, "request").mockResolvedValue({
      ...page,
      items: [],
      total: 0,
      next_cursor: null,
      pending_projection: 146,
      projection_current: false,
    });
    render(<RetainedHistory api={api} workspaceId="fictional" revision={22} />);
    expect(
      await screen.findByText(t("history.projectionPending", { count: 146 })),
    ).toBeVisible();
    expect(
      screen.queryByText(t("history.retainedEmpty")),
    ).not.toBeInTheDocument();
  });
  it("retains already read rows and refuses a changed-revision continuation", async () => {
    const api = new Api();
    const user = userEvent.setup();
    vi.spyOn(api, "request")
      .mockResolvedValueOnce(page)
      .mockResolvedValueOnce({
        ...page,
        revision: 23,
        items: [
          { ...observation, id: "foreign", employer: "Unexpected Example" },
        ],
      });
    render(<RetainedHistory api={api} workspaceId="fictional" revision={22} />);
    await screen.findByText("Northstar Example · Analyst");
    await user.click(
      screen.getByRole("button", { name: t("history.moreRetained") }),
    );
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Northstar Example · Analyst" }),
    ).toBeVisible();
    expect(
      screen.queryByText("Unexpected Example · Analyst"),
    ).not.toBeInTheDocument();
  });
  it("refuses a response pretending an observation is a canonical linked event", async () => {
    const api = new Api();
    vi.spyOn(api, "request").mockResolvedValue({
      ...page,
      items: [
        {
          ...observation,
          case_id: "invented-case",
          canonical_activity_created: true,
        },
      ],
    });
    render(<RetainedHistory api={api} workspaceId="fictional" revision={22} />);
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(
      screen.queryByText("Northstar Example · Analyst"),
    ).not.toBeInTheDocument();
  });
  it("refreshes a newly built derived projection without requiring a business revision", async () => {
    const api = new Api();
    const user = userEvent.setup();
    vi.spyOn(api, "request")
      .mockResolvedValueOnce({
        ...page,
        items: [],
        total: 0,
        next_cursor: null,
        pending_projection: 2,
        projection_current: false,
      })
      .mockResolvedValueOnce({ ...page, next_cursor: null });
    vi.spyOn(api, "command");
    render(<RetainedHistory api={api} workspaceId="fictional" revision={22} />);
    await screen.findByText(t("history.projectionPending", { count: 2 }));
    await user.click(screen.getByRole("button", { name: t("common.refresh") }));
    expect(
      await screen.findByRole("heading", {
        name: "Northstar Example · Analyst",
      }),
    ).toBeVisible();
    expect(
      screen.queryByText(t("history.projectionPending", { count: 2 })),
    ).not.toBeInTheDocument();
    expect(api.command).not.toHaveBeenCalled();
  });
});
