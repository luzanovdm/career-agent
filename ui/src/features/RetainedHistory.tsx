import { useEffect, useRef, useState } from "react";
import type { Api } from "../api/client";
import { safeLink } from "../api/client";
import { t, errorText } from "../app/i18n";
import { Button, Disclosure, Link, Notice } from "../ui/controls";

export interface RetainedObservation {
  format: "career-agent.history-observation/1";
  id: string;
  original_status: string;
  event_kind: string;
  evidence_level: string;
  employer: string;
  role: string;
  role_url: string | null;
  date: {
    text: string;
    precision: "exact" | "approximate" | "unknown";
    occurred_at: string | null;
  };
  channel: string;
  evidence: string | null;
  source: {
    record_history_id: number;
    sha256: string;
    locator: string;
    kind: string;
  };
  historical_opportunity_reference: string | null;
  provider_message_id: string | null;
  provider_thread_id: string | null;
  case_id: null;
  scope: "unlinked";
  canonical_activity_created: false;
}
export interface RetainedHistoryPage {
  workspace_id: string;
  revision: number;
  items: RetainedObservation[];
  total: number;
  next_cursor: string | null;
  pending_projection: number;
  projection_current: boolean;
}
const statuses = new Set([
  "sent",
  "uncertain",
  "bounced",
  "rejected",
  "receipt",
  "follow_up",
  "unknown",
]);
const levels = new Set(["user_reported", "provider_observed", "unknown"]);

/** Unlinked observations remain separate from canonical case activity and send counts. */
export function RetainedHistory({
  api,
  workspaceId,
  revision,
}: {
  api: Api;
  workspaceId: string;
  revision: number;
}) {
  const [page, setPage] = useState<RetainedHistoryPage>();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Error>();
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const read = (cursor?: string, signal?: AbortSignal) =>
    api.request<RetainedHistoryPage>(
      "/api/v1/history/observations?" +
        new URLSearchParams({ limit: "25", ...(cursor ? { cursor } : {}) }),
      { signal },
    );
  const validate = (result: RetainedHistoryPage) => {
    if (
      result.workspace_id !== workspaceId ||
      result.revision !== revision ||
      !Array.isArray(result.items) ||
      result.items.some(
        (item) =>
          item.case_id !== null ||
          item.scope !== "unlinked" ||
          item.canonical_activity_created !== false,
      )
    )
      throw new Error(
        "History observation snapshot changed or has invalid scope.",
      );
    return result;
  };
  useEffect(() => {
    const controller = new AbortController();
    generation.current++;
    setPage(undefined);
    setPending(true);
    setFailure(undefined);
    void read(undefined, controller.signal)
      .then(validate)
      .then((result) => {
        if (!controller.signal.aborted) setPage(result);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setFailure(error);
      })
      .finally(() => {
        if (!controller.signal.aborted) setPending(false);
      });
    return () => {
      controller.abort();
      generation.current++;
    };
  }, [api, workspaceId, revision, retry]);
  const more = async () => {
    if (!page?.next_cursor || pending) return;
    const request = generation.current;
    setPending(true);
    setFailure(undefined);
    try {
      const result = validate(await read(page.next_cursor));
      if (request === generation.current)
        setPage({ ...result, items: [...page.items, ...result.items] });
    } catch (error) {
      if (request === generation.current) setFailure(error as Error);
    } finally {
      if (request === generation.current) setPending(false);
    }
  };
  return (
    <section
      className="panel retained-history"
      aria-label={t("history.retainedTitle")}
    >
      <div className="section-heading">
        <h2>{t("history.retainedTitle")}</h2>
        <Button
          isDisabled={pending}
          onPress={() => setRetry((value) => value + 1)}
        >
          {t("common.refresh")}
        </Button>
      </div>
      <p className="help">{t("history.retainedExplanation")}</p>
      {failure && (
        <Notice error>
          {errorText(failure)}{" "}
          <Button onPress={() => setRetry((value) => value + 1)}>
            {t("common.retry")}
          </Button>
        </Notice>
      )}
      {pending && <p role="status">{t("common.loading")}</p>}
      {page && (
        <>
          {(!page.projection_current || page.pending_projection > 0) && (
            <Notice>
              {t("history.projectionPending", {
                count: page.pending_projection,
              })}
            </Notice>
          )}
          {page.total === 0 && page.pending_projection === 0 && (
            <p>{t("history.retainedEmpty")}</p>
          )}
          {page.total > 0 && (
            <p>
              {t("history.retainedProgress", {
                shown: page.items.length,
                total: page.total,
              })}
            </p>
          )}
          <ol className="history-list">
            {page.items.map((item) => (
              <li key={item.id}>
                <h3>
                  {item.employer || t("history.employerUnknown")}
                  {item.role ? " · " + item.role : ""}
                </h3>
                <p>
                  {t("history.originalStatus", {
                    status: statuses.has(item.original_status)
                      ? t(`history.status.${item.original_status}`)
                      : item.original_status,
                  })}
                </p>
                <p>
                  {item.date.text || t("history.dateUnknown")} ·{" "}
                  {t(`history.precision.${item.date.precision}`)}
                </p>
                <p>{t("history.unlinked")}</p>
                {item.evidence && <p>{item.evidence}</p>}
                {item.role_url && safeLink(item.role_url) && (
                  <Link
                    href={safeLink(item.role_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    referrerPolicy="no-referrer"
                  >
                    {t("history.originalRoleLink")}
                  </Link>
                )}
                <Disclosure title={t("history.observationDetails")}>
                  <dl>
                    <dt>{t("history.evidenceLevel")}</dt>
                    <dd>
                      {levels.has(item.evidence_level)
                        ? t(`history.level.${item.evidence_level}`)
                        : item.evidence_level}
                    </dd>
                    <dt>{t("history.eventKind")}</dt>
                    <dd>
                      {[
                        "initial_application",
                        "follow_up",
                        "auto_receipt",
                        "rejection",
                        "bounce",
                        "unknown",
                      ].includes(item.event_kind)
                        ? t(`history.event.${item.event_kind}`)
                        : item.event_kind || t("common.none")}
                    </dd>
                    <dt>{t("history.channel")}</dt>
                    <dd>{item.channel || t("common.none")}</dd>
                    <dt>{t("history.source")}</dt>
                    <dd>
                      {safeLink(item.source.locator) ? (
                        <Link
                          href={safeLink(item.source.locator)}
                          target="_blank"
                          rel="noopener noreferrer"
                          referrerPolicy="no-referrer"
                        >
                          {item.source.locator}
                        </Link>
                      ) : (
                        item.source.locator || t("common.none")
                      )}
                    </dd>
                    <dt>{t("history.originalRoleLink")}</dt>
                    <dd>{item.role_url || t("common.none")}</dd>
                    <dt>{t("history.originalTimestamp")}</dt>
                    <dd>{item.date.occurred_at || t("history.dateUnknown")}</dd>
                  </dl>
                  <Disclosure title={t("common.details")}>
                    <dl>
                      <dt>{t("history.originalRoleReference")}</dt>
                      <dd>
                        {item.historical_opportunity_reference ||
                          t("common.none")}
                      </dd>
                      <dt>{t("history.providerMessage")}</dt>
                      <dd>{item.provider_message_id || t("common.none")}</dd>
                      <dt>{t("history.providerThread")}</dt>
                      <dd>{item.provider_thread_id || t("common.none")}</dd>
                      <dt>{t("history.retainedRecord")}</dt>
                      <dd>{item.source.record_history_id}</dd>
                      <dt>{t("history.hash")}</dt>
                      <dd>{item.source.sha256}</dd>
                    </dl>
                  </Disclosure>
                </Disclosure>
              </li>
            ))}
          </ol>
          {page.next_cursor && (
            <Button onPress={() => void more()} isDisabled={pending}>
              {t("history.moreRetained")}
            </Button>
          )}
        </>
      )}
    </section>
  );
}
