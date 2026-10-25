import type {
  CaseDetail,
  CasePage,
  Changes,
  Column,
  CommandInputs,
  ContactPage,
  Context,
  Receipt,
  Selection,
  Snapshot,
  AgentIntent,
  AgentHandoff,
  BoardPage,
  PacketPage,
  VersionPage,
} from "./types";
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public revision?: number,
  ) {
    super(message);
  }
}
export class UncertainCommand extends Error {
  constructor(public request_id: string) {
    super(
      "The save response could not be confirmed. Check its receipt before retrying. Your draft is retained.",
    );
  }
}
export class Api {
  private csrf = "";
  private attempts = new Map<
    string,
    { request_id: string; body: string; uncertain?: boolean }
  >();
  async session(capability?: string): Promise<void> {
    const r = await this.request<{ csrf_token: string; protocol: string }>(
      "/api/v1/session",
      {
        method: "POST",
        body: JSON.stringify(capability ? { capability } : {}),
      },
    );
    if (r.protocol !== "career-agent.local/1")
      throw new Error("Unsupported local runtime protocol.");
    this.csrf = r.csrf_token;
  }
  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!path.startsWith("/api/v1/"))
      throw new Error("Only local application API routes are supported.");
    const response = await fetch(path, {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init.body
          ? { "Content-Type": "application/json", "X-CSRF-Token": this.csrf }
          : {}),
        ...init.headers,
      },
    });
    const data = await response.json();
    if (!response.ok)
      throw new ApiError(
        response.status,
        data.error?.code ?? "REQUEST_FAILED",
        data.error?.message ??
          "The local runtime could not complete the request.",
        data.revision,
      );
    return data as T;
  }
  context(signal?: AbortSignal) {
    return this.request<Context>("/api/v1/context", { signal });
  }
  board(
    params: { track_id?: string; q?: string; closed?: boolean },
    signal?: AbortSignal,
  ) {
    return this.request<BoardPage>(
      "/api/v1/board?" +
        new URLSearchParams({
          limit: "50",
          ...Object.fromEntries(
            Object.entries(params)
              .filter(([, value]) => value !== undefined && value !== "")
              .map(([key, value]) => [key, String(value)]),
          ),
        }),
      { signal },
    );
  }
  cases(
    params: {
      view: "board" | "table";
      column?: Column;
      track_id?: string;
      q?: string;
      closed?: boolean;
      cursor?: string;
    },
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams({
      limit: "50",
      ...Object.fromEntries(
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== "")
          .map(([k, v]) => [k, String(v)]),
      ),
    });
    return this.request<CasePage>(`/api/v1/cases?${query}`, { signal });
  }
  contacts(q: string, cursor?: string, signal?: AbortSignal) {
    const query = new URLSearchParams({
      limit: "50",
      q,
      ...(cursor ? { cursor } : {}),
    });
    return this.request<ContactPage>(`/api/v1/contacts?${query}`, { signal });
  }
  detail(id: string, signal?: AbortSignal) {
    return this.request<CaseDetail>(`/api/v1/cases/${encodeURIComponent(id)}`, {
      signal,
    });
  }
  contactPackets(id: string, cursor?: string, signal?: AbortSignal) {
    return this.request<PacketPage>(
      `/api/v1/contacts/${encodeURIComponent(id)}/packets?` +
        new URLSearchParams({ limit: "50", ...(cursor ? { cursor } : {}) }),
      { signal },
    );
  }
  versions(id: string, cursor?: string, signal?: AbortSignal) {
    return this.request<VersionPage>(
      `/api/v1/packets/${encodeURIComponent(id)}/versions?` +
        new URLSearchParams({ limit: "50", ...(cursor ? { cursor } : {}) }),
      { signal },
    );
  }
  selection(id: string, signal?: AbortSignal, version_id?: string) {
    return this.request<Selection & Snapshot>(
      `/api/v1/packets/${encodeURIComponent(id)}/selection` +
        (version_id ? "?" + new URLSearchParams({ version_id }) : ""),
      { signal },
    );
  }
  changes(after: number, signal?: AbortSignal) {
    return this.request<Changes>(`/api/v1/changes?after=${after}`, { signal });
  }
  receipt(id: string) {
    return this.request<Receipt>(`/api/v1/commands/${encodeURIComponent(id)}`);
  }
  localization(locale: string, signal?: AbortSignal) {
    return this.request<
      Snapshot & {
        locale: string;
        fallback_locale: string;
        catalog: Record<string, string | Record<string, string>>;
        plural_categories: string[];
      }
    >("/api/v1/localization?" + new URLSearchParams({ locale }), { signal });
  }
  agentIntent(
    intent: AgentIntent,
    case_id?: string,
    signal?: AbortSignal,
    track_id?: string,
    packet_id?: string,
    version_id?: string,
  ) {
    return this.request<AgentHandoff>(
      "/api/v1/agent-intent?" +
        new URLSearchParams({
          intent,
          ...(case_id ? { case_id } : {}),
          ...(track_id ? { track_id } : {}),
          ...(packet_id ? { packet_id } : {}),
          ...(version_id ? { version_id } : {}),
        }),
      { signal },
    );
  }
  async command<K extends keyof CommandInputs>(
    intent: K,
    input: CommandInputs[K],
    expected_revision: number,
  ): Promise<Receipt> {
    const key = JSON.stringify({ intent, input, expected_revision });
    let attempt = this.attempts.get(key);
    if (!attempt) {
      const request_id = crypto.randomUUID();
      attempt = {
        request_id,
        body: JSON.stringify({ request_id, expected_revision, intent, input }),
      };
      this.attempts.set(key, attempt);
    }
    let receipt: Receipt;
    if (attempt.uncertain) {
      try {
        receipt = await this.receipt(attempt.request_id);
        if (
          receipt.request_id !== attempt.request_id ||
          !["satisfied", "partial"].includes(receipt.outcome) ||
          receipt.external_actions?.performed !== 0
        )
          throw new UncertainCommand(attempt.request_id);
        this.attempts.delete(key);
        return receipt;
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404))
          throw new UncertainCommand(attempt.request_id);
        // A verified missing receipt permits the same idempotent request below.
      }
    }
    try {
      receipt = await this.request<Receipt>("/api/v1/commands", {
        method: "POST",
        body: attempt.body,
      });
    } catch (error) {
      if (error instanceof ApiError) {
        this.attempts.delete(key);
        throw error;
      }
      attempt.uncertain = true;
      try {
        receipt = await this.receipt(attempt.request_id);
      } catch (statusError) {
        if (statusError instanceof ApiError && statusError.status === 404)
          throw new ApiError(
            0,
            "UNCONFIRMED_SAVE",
            "No committed receipt was found. Your draft is retained; retry uses the same request ID.",
          );
        throw new UncertainCommand(attempt.request_id);
      }
    }
    if (
      receipt.request_id !== attempt.request_id ||
      !["satisfied", "partial"].includes(receipt.outcome) ||
      receipt.external_actions?.performed !== 0
    )
      throw new UncertainCommand(attempt.request_id);
    this.attempts.delete(key);
    return receipt;
  }
}
export const api = new Api();
export function takeLaunchCapability(): string | null {
  const hash = window.location.hash;
  const capability = new URLSearchParams(hash.replace(/^#/, "")).get("launch");
  if (capability)
    history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
  return capability;
}
export function safeLink(value: string): string | undefined {
  try {
    const url = new URL(value, location.origin);
    return ["http:", "https:", "mailto:"].includes(url.protocol)
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
export function artifactLink(value: string): string | undefined {
  try {
    const url = new URL(value, location.origin);
    return url.origin === location.origin &&
      /^\/api\/v1\/artifacts\/[^/]+\/download$/.test(url.pathname) &&
      !url.search &&
      !url.hash
      ? url.pathname
      : undefined;
  } catch {
    return undefined;
  }
}
