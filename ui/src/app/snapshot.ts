import { useCallback, useEffect, useRef, useState } from "react";
import i18next from "i18next";
import { Api, ApiError } from "../api/client";
import {
  columns,
  type CaseDetail,
  type CasePage,
  type ContactPage,
  type Context,
  type Change,
  type Snapshot,
} from "../api/types";
import { applyLocale } from "./i18n";
export interface Filters {
  q: string;
  track_id: string;
  closed: boolean;
}
export interface ViewSnapshot {
  context: Context;
  pages: Record<string, CasePage>;
  contacts?: ContactPage;
  detail?: CaseDetail;
}
interface Cache {
  context?: Context;
  contextDirty: boolean;
  overview?: { key: string; pages: Record<string, CasePage>; valid: boolean };
  contacts?: { q: string; page: ContactPage; valid: boolean };
  detail?: { key: string; value: CaseDetail; valid: boolean };
  localeDirty: boolean;
}
/** Memory-only bounded projections. Hidden overview pages never load when a detail opens. */
export function useSnapshot(
  api: Api,
  ready: boolean,
  section: string,
  view: "board" | "table",
  filters: Filters,
  selected: string | null,
  selectedPacket: string | null,
) {
  const [data, setData] = useState<ViewSnapshot>(),
    [error, setError] = useState<Error>(),
    [refreshing, setRefreshing] = useState(false),
    [tick, setTick] = useState(0),
    [desired, setDesired] = useState<{
      key: string;
      counts: Record<string, number>;
    }>({ key: "", counts: {} });
  const cache = useRef<Cache>({ contextDirty: true, localeDirty: false }),
    generation = useRef(0),
    minimum = useRef(0),
    workspace = useRef<string | undefined>(undefined);
  const key = JSON.stringify({ view, ...filters });
  const desiredCounts = desired.key === key ? desired.counts : {};
  const invalidate = useCallback((revision = 0, change?: Change) => {
    minimum.current = Math.max(minimum.current, revision);
    const current = cache.current;
    current.contextDirty = true;
    const contextOnly =
      change &&
      change.kinds.length > 0 &&
      change.kinds.every((kind) =>
        ["preferences", "preference", "profile", "locale"].includes(kind),
      );
    if (change?.kinds.includes("locale")) current.localeDirty = true;
    if (!contextOnly) {
      if (current.overview) current.overview.valid = false;
      if (current.contacts) current.contacts.valid = false;
      if (current.detail) {
        const dependent =
          !change ||
          !change.ids.length ||
          change.ids.includes(current.detail.value.case.id) ||
          change.ids.includes(
            current.detail.value.selection?.packet_id ?? "",
          ) ||
          change.kinds.some((kind) =>
            [
              "source",
              "claim",
              "answer",
              "person",
              "contact",
              "track",
              "version",
            ].includes(kind),
          );
        if (dependent) current.detail.valid = false;
      }
    }
    setTick((value) => value + 1);
  }, []);
  useEffect(() => {
    if (!ready) return;
    const request = ++generation.current,
      controller = new AbortController();
    setRefreshing(true);
    async function read() {
      for (let retry = 0; retry < 3; retry++) {
        try {
          const current = cache.current,
            readSnapshots: Snapshot[] = [];
          const contextPromise =
            current.context && !current.contextDirty
              ? Promise.resolve(current.context)
              : api.context(controller.signal);
          const overviewKey = key;
          const overviewPromise =
            section === "cases" && !selected
              ? (async () => {
                  let pages: Record<string, CasePage>;
                  if (
                    current.overview?.key === overviewKey &&
                    current.overview.valid
                  )
                    pages = { ...current.overview.pages };
                  else if (view === "board") {
                    const board = await api.board(filters, controller.signal);
                    readSnapshots.push(board);
                    pages = Object.fromEntries(
                      columns.map((column) => [
                        column,
                        {
                          workspace_id: board.workspace_id,
                          revision: board.revision,
                          ...board.columns[column],
                          counts: board.counts,
                          qualified_people: board.qualified_people,
                        },
                      ]),
                    );
                  } else {
                    const page = await api.cases(
                      { view, ...filters },
                      controller.signal,
                    );
                    readSnapshots.push(page);
                    pages = { table: page };
                  }
                  for (const column of view === "board" ? columns : ["table"]) {
                    let page = pages[column];
                    const wanted = (desiredCounts[column] ?? 1) * 50;
                    while (page.items.length < wanted && page.next_cursor) {
                      const more = await api.cases(
                        {
                          view,
                          ...filters,
                          ...(column !== "table"
                            ? { column: column as (typeof columns)[number] }
                            : {}),
                          cursor: page.next_cursor,
                        },
                        controller.signal,
                      );
                      readSnapshots.push(more);
                      if (more.revision !== page.revision)
                        throw new ApiError(
                          409,
                          "REVISION_CONFLICT",
                          "Pagination snapshot changed.",
                        );
                      page = { ...more, items: [...page.items, ...more.items] };
                      pages[column] = page;
                    }
                  }
                  return pages;
                })()
              : Promise.resolve(current.overview?.pages ?? {});
          const contactsPromise =
            section === "contacts"
              ? (async () => {
                  let page: ContactPage;
                  if (
                    current.contacts?.q === filters.q &&
                    current.contacts.valid
                  )
                    page = current.contacts.page;
                  else {
                    page = await api.contacts(
                      filters.q,
                      undefined,
                      controller.signal,
                    );
                    readSnapshots.push(page);
                  }
                  const wanted = (desiredCounts.contacts ?? 1) * 50;
                  while (page.items.length < wanted && page.next_cursor) {
                    const more = await api.contacts(
                      filters.q,
                      page.next_cursor,
                      controller.signal,
                    );
                    readSnapshots.push(more);
                    if (more.revision !== page.revision)
                      throw new ApiError(
                        409,
                        "REVISION_CONFLICT",
                        "Pagination snapshot changed.",
                      );
                    page = { ...more, items: [...page.items, ...more.items] };
                  }
                  return page;
                })()
              : Promise.resolve(undefined);
          const detailKey = selected + ":" + (selectedPacket ?? "");
          const detailPromise =
            selected && section === "cases"
              ? (async () => {
                  if (current.detail?.key === detailKey && current.detail.valid)
                    return current.detail.value;
                  const detail = await api.detail(selected, controller.signal);
                  readSnapshots.push(detail);
                  if (selectedPacket) {
                    const selection = await api.selection(
                      selectedPacket,
                      controller.signal,
                    );
                    readSnapshots.push(selection);
                    return { ...detail, selection };
                  }
                  return detail;
                })()
              : Promise.resolve(undefined);
          let [context, pages, contacts, detail] = await Promise.all([
            contextPromise,
            overviewPromise,
            contactsPromise,
            detailPromise,
          ]);
          if (controller.signal.aborted || request !== generation.current)
            return;
          if (workspace.current && context.workspace_id !== workspace.current)
            throw new Error("Workspace identity changed.");
          if (
            readSnapshots.some((value) => value.revision > context.revision)
          ) {
            context = await api.context(controller.signal);
            current.context = context;
            current.contextDirty = false;
          }
          if (
            readSnapshots.some(
              (value) =>
                value.workspace_id !== context.workspace_id ||
                value.revision !== context.revision,
            ) ||
            context.revision < minimum.current
          )
            throw new ApiError(409, "REVISION_CONFLICT", "Snapshot changed.");
          const locale = context.preferences.ui_locale ?? "en";
          if (i18next.language !== locale || current.localeDirty) {
            const localization = await api.localization(
              locale,
              controller.signal,
            );
            if (localization.revision !== context.revision)
              throw new ApiError(
                409,
                "REVISION_CONFLICT",
                "Locale snapshot changed.",
              );
            if (request !== generation.current || controller.signal.aborted)
              return;
            await applyLocale({
              locale: localization.locale,
              plural_categories: localization.plural_categories,
              messages: localization.catalog,
            });
            current.localeDirty = false;
          }
          if (request !== generation.current || controller.signal.aborted)
            return;
          // A cached unaffected record remains valid at this transaction revision.
          if (detail) detail = { ...detail, revision: context.revision };
          current.context = context;
          current.contextDirty = false;
          if (section === "cases" && !selected)
            current.overview = { key: overviewKey, pages, valid: true };
          if (contacts)
            current.contacts = { q: filters.q, page: contacts, valid: true };
          if (detail)
            current.detail = { key: detailKey, value: detail, valid: true };
          workspace.current = context.workspace_id;
          minimum.current = context.revision;
          setData({ context, pages, contacts, detail });
          setError(undefined);
          return;
        } catch (error) {
          if (controller.signal.aborted) return;
          if (error instanceof ApiError && error.status === 409 && retry < 2) {
            const current = cache.current;
            current.contextDirty = true;
            if (current.overview) current.overview.valid = false;
            if (current.contacts) current.contacts.valid = false;
            if (current.detail) current.detail.valid = false;
            continue;
          }
          throw error;
        }
      }
    }
    void read()
      .catch((error) => {
        if (request === generation.current && !controller.signal.aborted)
          setError(error);
      })
      .finally(() => {
        if (request === generation.current) setRefreshing(false);
      });
    return () => controller.abort();
  }, [api, ready, section, view, key, selected, selectedPacket, tick, desired]);
  return {
    data,
    error,
    refreshing,
    invalidate,
    more: (column: string) =>
      setDesired((previous) => ({
        key,
        counts: {
          ...(previous.key === key ? previous.counts : {}),
          [column]:
            ((previous.key === key ? previous.counts[column] : undefined) ??
              1) + 1,
        },
      })),
  };
}
