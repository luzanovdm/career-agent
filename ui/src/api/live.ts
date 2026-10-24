import { Api, type ApiError } from "./client";
import type { Change } from "./types";
export type Connection =
  | "connecting"
  | "live"
  | "reconnecting"
  | "offline"
  | "hidden"
  | "reauthenticate";
/** SSE is invalidation only. Polling is bounded and never stores career data. */
export function connectLive(
  api: Api,
  workspace: string,
  initial: number,
  invalidate: (revision: number, change?: Change) => void,
  status: (value: Connection) => void,
) {
  let cursor = initial,
    source: EventSource | null = null,
    reconnect: ReturnType<typeof setTimeout> | undefined,
    poll: ReturnType<typeof setTimeout> | undefined,
    stopped = false,
    polling = false;
  const announce = (revision: number, change?: Change) => {
    if (revision > cursor) {
      cursor = revision;
      invalidate(revision, change);
    }
  };
  const errorStatus = (error: unknown) => {
    if ((error as ApiError).status === 401) {
      status("reauthenticate");
      stopped = true;
      clearTimeout(reconnect);
      clearTimeout(poll);
      source?.close();
      source = null;
      return true;
    }
    status("offline");
    return false;
  };
  const pollNow = async () => {
    if (stopped || document.hidden || polling) return;
    polling = true;
    try {
      const data = await api.changes(cursor);
      if (stopped) return;
      if (data.workspace_id !== workspace)
        throw new Error(
          "Workspace changed. Reopen through the trusted launcher.",
        );
      if (data.resync_required) {
        cursor = data.revision;
        invalidate(data.revision);
      } else
        for (const change of data.changes) announce(change.revision, change);
      if (!source || source.readyState !== 1) status("reconnecting");
    } catch (error) {
      if (errorStatus(error)) return;
    } finally {
      polling = false;
    }
    if (!stopped && !document.hidden) poll = setTimeout(pollNow, 2000);
  };
  const open = () => {
    if (stopped || document.hidden) return;
    status("connecting");
    source = new EventSource(`/api/v1/events?after=${cursor}`, {
      withCredentials: true,
    });
    source.onopen = () => status("live");
    source.addEventListener("change", (event) => {
      try {
        const change = JSON.parse((event as MessageEvent).data);
        if (change.workspace_id !== workspace) {
          void pollNow();
          return;
        }
        if (Number.isSafeInteger(change.revision))
          announce(change.revision, change);
      } catch {
        invalidate(cursor);
      }
    });
    source.addEventListener("resync", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        if (Number.isSafeInteger(data.revision)) {
          cursor = data.revision;
          invalidate(cursor);
        }
      } catch {
        invalidate(cursor);
      }
    });
    source.onerror = () => {
      source?.close();
      source = null;
      status("reconnecting");
      clearTimeout(poll);
      void pollNow();
      clearTimeout(reconnect);
      reconnect = setTimeout(open, 4000);
    };
  };
  const visibility = () => {
    clearTimeout(poll);
    clearTimeout(reconnect);
    source?.close();
    source = null;
    if (document.hidden) status("hidden");
    else {
      invalidate(cursor);
      open();
      void pollNow();
    }
  };
  const focus = () => {
    if (!document.hidden) {
      invalidate(cursor);
      if (!source) open();
    }
  };
  document.addEventListener("visibilitychange", visibility);
  window.addEventListener("focus", focus);
  open();
  return () => {
    stopped = true;
    source?.close();
    clearTimeout(poll);
    clearTimeout(reconnect);
    document.removeEventListener("visibilitychange", visibility);
    window.removeEventListener("focus", focus);
  };
}
