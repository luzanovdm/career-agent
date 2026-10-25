import { useEffect, useRef, useState } from "react";
import type { Api } from "../api/client";
import { safeLink } from "../api/client";
import { date, errorText, t } from "../app/i18n";
import { Button, Disclosure, Link, Notice } from "../ui/controls";
import type { EvidenceContext, EvidenceSource } from "./evidenceTypes";
export function SourceEvidence({
  api,
  sourceId,
  source,
  workspaceId,
  revision,
  label,
}: {
  api: Api;
  sourceId: string;
  source?: EvidenceSource;
  workspaceId?: string;
  revision?: number;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState<EvidenceSource>();
  const [failure, setFailure] = useState<Error>();
  const [pending, setPending] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    if (!open) return;
    const request = ++generation.current;
    const controller = new AbortController();
    setFailure(undefined);
    setSaved(undefined);
    if (source && !source.excerpt_truncated) {
      setSaved(source);
      setPending(false);
      return () => {
        controller.abort();
        generation.current++;
      };
    }
    setPending(true);
    void api
      .request<EvidenceContext>(
        "/api/v1/context?" + new URLSearchParams({ source_id: sourceId }),
        { signal: controller.signal },
      )
      .then((result) => {
        if (
          (workspaceId && result.workspace_id !== workspaceId) ||
          (revision !== undefined && result.revision !== revision) ||
          result.source?.id !== sourceId
        )
          throw new Error("Source snapshot changed.");
        if (request === generation.current && !controller.signal.aborted)
          setSaved(result.source);
      })
      .catch((error) => {
        if (request === generation.current && !controller.signal.aborted)
          setFailure(error);
      })
      .finally(() => {
        if (request === generation.current && !controller.signal.aborted)
          setPending(false);
      });
    return () => {
      controller.abort();
      generation.current++;
    };
  }, [api, open, sourceId, source, workspaceId, revision, retry]);
  const locator = saved?.locator ?? source?.locator;
  return (
    <div className="source-evidence">
      <Button
        size="small"
        aria-expanded={open}
        onPress={() => setOpen((value) => !value)}
      >
        {label ?? locator ?? t("evidence.openSource")}
      </Button>
      {open && (
        <section aria-label={t("evidence.sourceDetails")}>
          {pending && <p role="status">{t("common.loading")}</p>}
          {failure && (
            <Notice error>
              {errorText(failure)}{" "}
              <Button onPress={() => setRetry((value) => value + 1)}>
                {t("common.retry")}
              </Button>
            </Notice>
          )}
          {saved && (
            <>
              <p>
                {saved.readable
                  ? t("evidence.sourceReadable")
                  : t("evidence.sourceUnreadable")}
              </p>
              <p>
                {/^https?:\/\//i.test(saved.locator) &&
                safeLink(saved.locator) ? (
                  <Link
                    href={safeLink(saved.locator)}
                    target="_blank"
                    rel="noopener noreferrer"
                    referrerPolicy="no-referrer"
                  >
                    {saved.locator}
                  </Link>
                ) : (
                  saved.locator
                )}
              </p>
              <time dateTime={saved.observed_at}>
                {date(saved.observed_at)}
              </time>
              <blockquote>
                {saved.excerpt || t("evidence.noExcerpt")}
              </blockquote>
              <Disclosure title={t("common.details")}>
                <p>{saved.id}</p>
              </Disclosure>
            </>
          )}
        </section>
      )}
    </div>
  );
}
