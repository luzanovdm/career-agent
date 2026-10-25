import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Api } from "../src/api/client";
import { App } from "../src/app/App";
import { context, detail, contacts, page, board, handoff } from "./fixtures";

function setup() {
  const api = new Api();
  const source = structuredClone(detail);
  source.packets[0] = {
    ...source.packets[0],
    purpose: "application",
    person_name: "Jordan Example",
    is_primary: true,
  };
  source.packets.push(
    {
      id: "contact-a",
      purpose: "contact",
      person_id: "contact-jordan",
      person_name: "Jordan Example",
      selected_version_id: "va",
      case_id: source.case.id,
    },
    {
      id: "contact-b",
      purpose: "contact",
      person_id: "taylor",
      person_name: "Taylor Example",
      selected_version_id: "vb",
      case_id: source.case.id,
    },
    {
      id: "empty",
      purpose: "contact",
      person_id: "taylor",
      person_name: "Taylor Empty",
      selected_version_id: null,
      case_id: source.case.id,
    },
  );
  const selections = Object.fromEntries(
    ["contact-a", "contact-b"].map((id) => [
      id,
      {
        ...structuredClone(source.selection!),
        ...context,
        packet_id: id,
        purpose: "contact",
        slots: [
          {
            name: "message",
            text: `Exact saved ${id}`,
            sha256: id === "contact-a" ? "a".repeat(64) : "b".repeat(64),
            artifact_id: id,
            media_type: "text/markdown",
            download_url: `/api/v1/artifacts/${id}/download`,
          },
          {
            name: "interview",
            text: `Preparation ${id}`,
            sha256: "c".repeat(64),
            artifact_id: `prep-${id}`,
            media_type: "text/markdown",
            download_url: `/api/v1/artifacts/prep-${id}/download`,
          },
        ],
      },
    ]),
  );
  vi.spyOn(api, "board").mockResolvedValue(board());
  vi.spyOn(api, "context").mockResolvedValue({
    ...structuredClone(context),
    exports: [
      { kind: "csv", revision: 0, status: "stale" },
      { kind: "profile", revision: 1, status: "current" },
    ],
  });
  vi.spyOn(api, "cases").mockImplementation(async (params) =>
    page(params.column),
  );
  vi.spyOn(api, "detail").mockResolvedValue(source);
  vi.spyOn(api, "selection").mockImplementation(async (id) =>
    id === "packet-aurora"
      ? { ...context, ...source.selection! }
      : selections[id],
  );
  vi.spyOn(api, "contacts").mockResolvedValue(structuredClone(contacts));
  vi.spyOn(api, "contactPackets").mockResolvedValue({
    ...context,
    total: 3,
    next_cursor: null,
    items: source.packets.filter((p) => p.person_id === "contact-jordan"),
  });
  vi.spyOn(api, "changes").mockResolvedValue({
    ...context,
    changes: [],
    resync_required: false,
  });
  vi.spyOn(api, "command");
  vi.spyOn(api, "agentIntent").mockImplementation(
    async (intent, caseId, signal, track, packet) => ({
      ...handoff,
      descriptor: {
        ...handoff.descriptor,
        intent,
        selection_mode: "packet",
        scope: {
          ...handoff.descriptor.scope,
          case_ids: [caseId!],
          packet_ids: [packet!],
          version_ids: ["vb"],
        },
      },
    }),
  );
  return { api, source };
}
const openCase = async (user: ReturnType<typeof userEvent.setup>) =>
  user.click(
    await screen.findByRole("button", {
      name: "Open Aurora Example: Product engineer",
    }),
  );
const choose = async (
  user: ReturnType<typeof userEvent.setup>,
  name: RegExp,
) => {
  await user.click(
    await screen.findByRole("button", { name: /Saved packet$/ }),
  );
  await user.click(screen.getByRole("option", { name }));
};
describe("all saved packet navigation", () => {
  it("loads alternatives and their own preparation, preserves primary and opens exact packet handoff", async () => {
    const user = userEvent.setup();
    const { api } = setup();
    render(<App api={api} alreadyAuthenticated />);
    await openCase(user);
    await choose(user, /Contact message · Taylor Example/);
    expect(await screen.findByText("Exact saved contact-b")).toBeVisible();
    await user.click(
      screen.getByRole("tab", { name: "Interview preparation" }),
    );
    expect(screen.getByText("Preparation contact-b")).toBeVisible();
    await user.click(document.querySelector(".agent-entry")!);
    expect(
      await screen.findByRole("textbox", { name: "Prompt for Claude / Codex" }),
    ).toBeVisible();
    expect(api.agentIntent).toHaveBeenLastCalledWith(
      expect.any(String),
      detail.case.id,
      expect.any(AbortSignal),
      undefined,
      "contact-b",
      undefined,
    );
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }),
    );
    await user.click(screen.getByRole("button", { name: "Back to cases" }));
    await openCase(user);
    expect(await screen.findByText(/Hello Jordan,/)).toBeVisible();
    expect(api.command).not.toHaveBeenCalled();
  });
  it("opens a person's draft and returns to the same contact, then reopens it", async () => {
    const user = userEvent.setup();
    const { api } = setup();
    render(<App api={api} alreadyAuthenticated />);
    await screen.findByText("Aurora Example");
    await user.click(
      within(document.querySelector(".sidebar nav")!).getByRole("button", {
        name: "Contacts",
      }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Jordan Example" }),
    );
    const group = await screen.findByRole("region", {
      name: "Saved packets for Jordan Example",
    });
    await user.click(
      await within(group).findByRole("button", {
        name: /Contact message · Jordan Example/,
      }),
    );
    expect(await screen.findByText("Exact saved contact-a")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Back to contacts" }));
    const reopened = await screen.findByRole("region", {
      name: "Saved packets for Jordan Example",
    });
    await user.click(
      await within(reopened).findByRole("button", {
        name: /Contact message · Jordan Example/,
      }),
    );
    expect(await screen.findByText("Exact saved contact-a")).toBeVisible();
    expect(api.command).not.toHaveBeenCalled();
  });
  it("shows an unsaved empty packet without borrowing primary content", async () => {
    const user = userEvent.setup();
    const { api } = setup();
    render(<App api={api} alreadyAuthenticated />);
    await openCase(user);
    await choose(user, /Taylor Empty/);
    expect(
      await screen.findByRole("heading", { name: "No packet selected" }),
    ).toBeVisible();
    expect(screen.queryByText(/Hello Jordan,/)).not.toBeInTheDocument();
    expect(api.selection).not.toHaveBeenCalled();
  });
  it("reports stale exports independently of saved live data", async () => {
    const user = userEvent.setup();
    const { api } = setup();
    render(<App api={api} alreadyAuthenticated />);
    await user.click(
      await screen.findByRole("button", {
        name: "Static exports are out of date",
      }),
    );
    expect(screen.getByText(/Out of date · revision 0/)).toBeVisible();
    expect(screen.getByText(/Current · revision 1/)).toBeVisible();
    expect(
      screen.getByText(/Previously exported files do not update automatically/),
    ).toBeVisible();
    expect(api.command).not.toHaveBeenCalled();
  });
});
