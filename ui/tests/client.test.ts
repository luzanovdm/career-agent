import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  Api,
  ApiError,
  UncertainCommand,
  artifactLink,
  safeLink,
  takeLaunchCapability,
} from "../src/api/client";
import { receipt } from "./fixtures";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
describe("typed API and trust boundary", () => {
  beforeEach(() =>
    vi
      .spyOn(crypto, "randomUUID")
      .mockReturnValue(receipt.request_id as ReturnType<Crypto["randomUUID"]>),
  );
  it("clears capability before requests and resumes with an empty body on reload", async () => {
    history.replaceState(null, "", "/#launch=test-one-use");
    expect(takeLaunchCapability()).toBe("test-one-use");
    expect(location.hash).toBe("");
    const fetch = vi
      .fn()
      .mockResolvedValue(
        json({ csrf_token: "memory-only", protocol: "career-agent.local/1" }),
      );
    vi.stubGlobal("fetch", fetch);
    await new Api().session();
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({});
    expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
  });
  it("resolves a lost POST through its receipt instead of posting twice", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("lost"))
      .mockResolvedValueOnce(json(receipt));
    vi.stubGlobal("fetch", fetch);
    const result = await new Api().command(
      "case.note",
      { case_id: "case-aurora", text: "Draft" },
      1,
    );
    expect(result).toEqual(receipt);
    expect(fetch.mock.calls.map((call) => call[1].method ?? "GET")).toEqual([
      "POST",
      "GET",
    ]);
    expect(fetch.mock.calls[1][0]).toMatch(/^\/api\/v1\/commands\//);
  });
  it("retains request identity for a known unconfirmed retry", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("lost"))
      .mockResolvedValueOnce(
        json({ error: { code: "NOT_FOUND", message: "No receipt" } }, 404),
      )
      .mockResolvedValueOnce(
        json({ error: { code: "NOT_FOUND", message: "No receipt" } }, 404),
      )
      .mockResolvedValueOnce(json(receipt));
    vi.stubGlobal("fetch", fetch);
    const api = new Api();
    await expect(
      api.command("case.note", { case_id: "case-aurora", text: "Draft" }, 1),
    ).rejects.toMatchObject({ code: "UNCONFIRMED_SAVE" });
    await api.command(
      "case.note",
      { case_id: "case-aurora", text: "Draft" },
      1,
    );
    expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[3][1].body);
  });
  it("does not invent success when both response and receipt lookup fail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(
      new Api().command(
        "case.note",
        { case_id: "case-aurora", text: "Draft" },
        1,
      ),
    ).rejects.toBeInstanceOf(UncertainCommand);
  });
  it("exposes revision conflicts without overwriting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json(
          {
            error: { code: "REVISION_CONFLICT", message: "Changed" },
            revision: 4,
          },
          409,
        ),
      ),
    );
    await expect(
      new Api().command(
        "case.note",
        { case_id: "case-aurora", text: "Draft" },
        1,
      ),
    ).rejects.toEqual(new ApiError(409, "REVISION_CONFLICT", "Changed", 4));
  });
  it("does not allow document URLs to become arbitrary local files or executable links", () => {
    expect(artifactLink("/api/v1/artifacts/a/download")).toBe(
      "/api/v1/artifacts/a/download",
    );
    expect(
      artifactLink("https://external.example/api/v1/artifacts/a/download"),
    ).toBeUndefined();
    expect(
      artifactLink("/api/v1/artifacts/a/download?path=/private"),
    ).toBeUndefined();
    expect(safeLink("javascript:alert(1)")).toBeUndefined();
    expect(safeLink("file:///private")).toBeUndefined();
  });
});
