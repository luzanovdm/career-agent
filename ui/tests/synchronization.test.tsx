import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { Api } from "../src/api/client";
import { connectLive } from "../src/api/live";
import { useSnapshot } from "../src/app/snapshot";
import { useTheme } from "../src/app/theme";
import { context, page } from "./fixtures";
import { TestEvents } from "./setup";
describe("synchronization and theme ownership", () => {
  it("rejects an older generation even when the transport ignores AbortSignal", async () => {
    const api = new Api();
    let resolveOld!: (value: typeof context) => void;
    vi.spyOn(api, "context")
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve;
          }),
      )
      .mockResolvedValue({ ...context, revision: 2 });
    vi.spyOn(api, "cases").mockImplementation(async (params) =>
      page(params.column, 2),
    );
    const hook = renderHook(() =>
      useSnapshot(
        api,
        true,
        "cases",
        "table",
        { q: "", track_id: "", closed: true },
        null,
        null,
      ),
    );
    act(() => hook.result.current.invalidate(2));
    await waitFor(() =>
      expect(hook.result.current.data?.context.revision).toBe(2),
    );
    await act(async () => resolveOld(context));
    expect(hook.result.current.data?.context.revision).toBe(2);
  });
  it("reconnects with the durable cursor and polls on stream failure", async () => {
    vi.useFakeTimers();
    const api = new Api();
    const changes = vi.spyOn(api, "changes").mockResolvedValue({
      ...context,
      revision: 3,
      changes: [
        {
          cursor: 3,
          revision: 3,
          kinds: ["case"],
          ids: ["case-aurora"],
          projection_keys: ["cases"],
        },
      ],
      resync_required: false,
    });
    const invalidate = vi.fn(),
      status = vi.fn();
    const stop = connectLive(api, context.workspace_id, 1, invalidate, status);
    TestEvents.instances[0].change({
      workspace_id: context.workspace_id,
      revision: 2,
      cursor: 2,
    });
    TestEvents.instances[0].fail();
    await vi.advanceTimersByTimeAsync(0);
    expect(changes).toHaveBeenCalledWith(2);
    expect(invalidate).toHaveBeenCalledWith(
      3,
      expect.objectContaining({ revision: 3 }),
    );
    await vi.advanceTimersByTimeAsync(4000);
    expect(TestEvents.instances.at(-1)?.url).toBe("/api/v1/events?after=3");
    stop();
    expect(status).toHaveBeenCalledWith("reconnecting");
  });
  it("resyncs without manufacturing change rows and pauses hidden polling", async () => {
    vi.useFakeTimers();
    const api = new Api();
    vi.spyOn(api, "changes").mockResolvedValue({
      ...context,
      revision: 12,
      changes: [],
      resync_required: true,
    });
    const invalidate = vi.fn();
    const stop = connectLive(api, context.workspace_id, 1, invalidate, vi.fn());
    TestEvents.instances[0].fail();
    await vi.advanceTimersByTimeAsync(0);
    expect(invalidate).toHaveBeenCalledWith(12);
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    const calls = vi.mocked(api.changes).mock.calls.length;
    await vi.advanceTimersByTimeAsync(10000);
    expect(api.changes).toHaveBeenCalledTimes(calls);
    stop();
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
  });
  it("listens to OS appearance only in system mode", () => {
    const add = vi.fn(),
      remove = vi.fn();
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
      addEventListener: add,
      removeEventListener: remove,
    } as unknown as MediaQueryList);
    const hook = renderHook(
      ({ theme }: { theme: "system" | "light" | "dark" }) => useTheme(theme),
      { initialProps: { theme: "system" as "system" | "light" | "dark" } },
    );
    expect(document.documentElement.dataset.osTheme).toBe("dark");
    expect(add).toHaveBeenCalledOnce();
    hook.rerender({ theme: "light" });
    expect(remove).toHaveBeenCalledOnce();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.dataset.osTheme).toBeUndefined();
    hook.rerender({ theme: "dark" });
    expect(add).toHaveBeenCalledOnce();
  });
});
