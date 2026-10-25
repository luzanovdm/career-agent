import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, act, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Api, ApiError } from "../src/api/client";
import { App } from "../src/app/App";
import { Detail } from "../src/features/Detail";
import {
  context,
  detail,
  page,
  contacts,
  receipt,
  board,
  handoff,
} from "./fixtures";
import { TestEvents } from "./setup";
const noop = () => {};
function mockApi() {
  const api = new Api();
  vi.spyOn(api, "board").mockResolvedValue(board());
  vi.spyOn(api, "agentIntent").mockImplementation(
    async (intent, caseId, signal, track, packet) => ({
      ...handoff,
      descriptor: {
        ...handoff.descriptor,
        intent,
        ...(packet
          ? {
              selection_mode: "packet" as const,
              scope: { ...handoff.descriptor.scope, packet_ids: [packet] },
            }
          : {}),
      },
    }),
  );
  vi.spyOn(api, "context").mockResolvedValue(structuredClone(context));
  vi.spyOn(api, "cases").mockImplementation(async (params) =>
    page(params.column),
  );
  vi.spyOn(api, "detail").mockResolvedValue(structuredClone(detail));
  vi.spyOn(api, "contacts").mockResolvedValue(structuredClone(contacts));
  vi.spyOn(api, "changes").mockResolvedValue({
    ...context,
    changes: [],
    resync_required: false,
  });
  return api;
}
describe("editable canonical views", () => {
  it("shows distinct cases once across tracks and shares the table projection", async () => {
    const user = userEvent.setup();
    const api = mockApi();
    render(<App api={api} alreadyAuthenticated />);
    expect(
      await screen.findByRole("button", {
        name: "Open Aurora Example: Product engineer",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", {
        name: "Open Aurora Example: Product engineer",
      }),
    ).toHaveLength(1);
    expect(
      screen.getByText("3 distinct cases · 1 qualified person"),
    ).toBeInTheDocument();
    expect(api.board).toHaveBeenCalledTimes(1);
    expect(api.context).toHaveBeenCalledTimes(1);
    await user.click(screen.getByText("Table"));
    expect(
      await within(document.querySelector(".desktop-case-table")!).findByRole(
        "grid",
        { name: "Cases" },
      ),
    ).toBeInTheDocument();
    expect(api.cases).toHaveBeenLastCalledWith(
      expect.objectContaining({ view: "table" }),
      expect.any(AbortSignal),
    );
  });
  it("retains a failed note save and offers explicit conflict reconciliation", async () => {
    const user = userEvent.setup();
    const api = mockApi();
    vi.spyOn(api, "command").mockRejectedValue(
      new ApiError(409, "REVISION_CONFLICT", "New revision", 2),
    );
    const props = { api, onDirty: noop, refresh: noop, onPacket: noop };
    const view = render(<Detail {...props} detail={detail} />);
    const notes = screen.getByRole("textbox", { name: "Case notes" });
    await user.clear(notes);
    await user.type(notes, "My retained local draft");
    await user.click(
      screen.getAllByRole("button", { name: "Save changes" })[0],
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "save conflicts",
    );
    expect(notes).toHaveValue("My retained local draft");
    view.rerender(
      <Detail
        {...props}
        detail={{ ...detail, revision: 2, notes: "Other tab note" }}
      />,
    );
    expect(
      await screen.findByText(/Saved data changed while/),
    ).toBeInTheDocument();
    expect(notes).toHaveValue("My retained local draft");
    await user.click(
      screen.getByRole("button", { name: "Keep draft and use current base" }),
    );
    await user.click(
      screen.getAllByRole("button", { name: "Save changes" })[0],
    );
    expect(api.command).toHaveBeenLastCalledWith(
      "case.note",
      { case_id: detail.case.id, text: "My retained local draft" },
      2,
    );
  });
  it("retains partial-save drafts and shows per-item issues", async () => {
    const user = userEvent.setup();
    const api = mockApi();
    vi.spyOn(api, "command").mockResolvedValue({
      ...receipt,
      outcome: "partial",
      issues: [
        {
          code: "REVIEW_REQUIRED",
          message: "Material review remains incomplete",
        },
      ],
    });
    render(
      <Detail
        detail={detail}
        api={api}
        onDirty={noop}
        refresh={noop}
        onPacket={noop}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Edit draft" }));
    const material = screen.getByRole("textbox", { name: "Message draft" });
    await user.type(material, "\nDraft addition");
    await user.click(
      screen.getAllByRole("button", { name: "Save changes" })[0],
    );
    expect(
      (
        await screen.findAllByText(
          "The selected draft needs fact and tone review.",
        )
      )[0],
    ).toBeInTheDocument();
    expect((material as HTMLTextAreaElement).value).toContain("Draft addition");
    expect(screen.getAllByText("Unsaved changes").length).toBeGreaterThan(0);
    expect(api.command).toHaveBeenLastCalledWith(
      "packet.save",
      expect.not.objectContaining({ review: expect.anything() }),
      1,
    );
  });
  it("complex actions bind a prompt without executing a command and retain keyboard fallback", async () => {
    const user = userEvent.setup();
    const api = mockApi();
    const command = vi.spyOn(api, "command");
    render(
      <Detail
        detail={detail}
        api={api}
        onDirty={noop}
        refresh={noop}
        onPacket={noop}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: "Prepare materials with agent" }),
    );
    const prompt = await screen.findByRole("textbox", {
      name: "Prompt for Claude / Codex",
    });
    expect(prompt).toHaveValue(handoff.prompt);
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
      new Error("denied"),
    );
    await user.click(screen.getByRole("button", { name: "Copy prompt" }));
    expect(
      await screen.findByText(/Clipboard access failed/),
    ).toBeInTheDocument();
    expect(prompt).toHaveFocus();
    expect(command).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(
      screen.getByRole("button", { name: "Prepare materials with agent" }),
    ).toHaveFocus();
  });
  it("warns before leaving dirty text and preserves drafts on live invalidation", async () => {
    const user = userEvent.setup();
    const api = mockApi();
    render(<App api={api} alreadyAuthenticated />);
    await user.click(
      await screen.findByRole("button", {
        name: "Open Aurora Example: Product engineer",
      }),
    );
    await user.type(
      await screen.findByRole("textbox", { name: "Case notes" }),
      " Local edit",
    );
    vi.mocked(api.context).mockResolvedValue({ ...context, revision: 2 });
    vi.mocked(api.board).mockResolvedValue(board(2));
    vi.mocked(api.cases).mockImplementation(async (params) =>
      page(params.column, 2),
    );
    vi.mocked(api.detail).mockResolvedValue({
      ...detail,
      revision: 2,
      notes: "External change",
    });
    await act(async () => {
      TestEvents.instances[0].change({
        workspace_id: context.workspace_id,
        cursor: 2,
        revision: 2,
        kinds: ["case"],
        ids: [detail.case.id],
        projection_keys: ["cases"],
      });
    });
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "Case notes" })).toHaveValue(
        "Private note before editing. Local edit",
      ),
    );
    expect(screen.getByText(/Saved data changed while/)).toBeInTheDocument();
    await user.click(
      screen.getAllByRole("button", { name: "Profile & tracks" })[0],
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Discard unsaved changes?",
    );
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(
      screen.getByRole("textbox", { name: "Case notes" }),
    ).toBeInTheDocument();
  });
});
