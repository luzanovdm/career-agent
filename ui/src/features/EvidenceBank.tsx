import { useEffect, useRef, useState } from "react";
import type { Api } from "../api/client";
import { artifactLink, safeLink } from "../api/client";
import { date, errorText, number, t } from "../app/i18n";
import {
  Button,
  Disclosure,
  Link,
  Notice,
  Tab,
  TabList,
  TabPanel,
  Tabs,
} from "../ui/controls";
import type {
  EvidenceAnswer,
  EvidenceClaim,
  EvidenceContext,
  EvidenceSource,
} from "./evidenceTypes";
import { SourceEvidence } from "./SourceEvidence";

const technical =
  /(?:^id$|_ids?$|sha256|^version$|^kind$|^path$|^source_statuses_preserved$|^record_history_id$)/;
const labels: Record<string, string> = {
  start: "evidence.field.start",
  end: "evidence.field.end",
  start_date: "evidence.field.start",
  end_date: "evidence.field.end",
  from: "evidence.field.start",
  to: "evidence.field.end",
  company: "evidence.field.company",
  employer: "evidence.field.company",
  role: "evidence.field.role",
  title: "evidence.field.role",
  position: "evidence.field.role",
  description: "evidence.field.description",
  contribution: "evidence.field.contribution",
  contributions: "evidence.field.contribution",
  result: "evidence.field.result",
  results: "evidence.field.result",
  statement: "evidence.field.statement",
  question: "evidence.field.question",
  question_key: "evidence.field.question",
  answer: "evidence.field.answer",
  value: "evidence.field.value",
  status: "evidence.field.status",
  disposition: "evidence.field.status",
  original_disposition: "evidence.field.status",
  language: "profile.documentLanguage",
  amount: "evidence.field.amount",
  currency: "evidence.field.currency",
  period: "evidence.field.period",
  unit: "evidence.units",
  units: "evidence.units",
  priority: "evidence.field.priority",
  evidence: "evidence.supportingNote",
  notes: "detail.notes",
  current_assessment: "evidence.field.assessment",
  current_next_action: "cases.nextAction",
  reason: "evidence.field.reason",
  source_status: "evidence.field.sourceStatus",
  identity_confidence: "evidence.field.identityConfidence",
  url: "evidence.field.url",
  topic: "evidence.field.topic",
  scope: "evidence.scope",
  source: "evidence.sourceDetails",
  note: "evidence.supportingNote",
};
function words(value: string) {
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_.-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
function fieldName(key: string) {
  return labels[key] ? t(labels[key]) : words(key);
}
function parsedEvidence(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
function TextValue({ value }: { value: string }) {
  const [full, setFull] = useState(false);
  const shown = full ? value : value.slice(0, 1000);
  return (
    <>
      <p className="evidence-text">
        {safeLink(value) && /^https?:\/\//i.test(value) ? (
          <Link
            href={safeLink(value)}
            target="_blank"
            rel="noopener noreferrer"
            referrerPolicy="no-referrer"
          >
            {shown}
          </Link>
        ) : (
          shown
        )}
      </p>
      {value.length > 1000 && (
        <Button size="small" onPress={() => setFull((value) => !value)}>
          {t(full ? "evidence.collapseText" : "evidence.readFull")}
        </Button>
      )}
    </>
  );
}
/** A readable value tree, never executable JSON or a browser business-state copy. */
export function EvidenceValue({
  value,
  api,
  workspaceId,
  revision,
}: {
  value: unknown;
  api: Api;
  workspaceId?: string;
  revision?: number;
}) {
  const [shown, setShown] = useState(10);
  if (value === null || value === undefined)
    return <span>{t("common.none")}</span>;
  if (typeof value === "string") return <TextValue value={value} />;
  if (typeof value === "boolean")
    return <span>{t(value ? "evidence.yes" : "evidence.no")}</span>;
  if (typeof value === "number") return <span>{number(value)}</span>;
  if (Array.isArray(value))
    return (
      <>
        <ol>
          {value.slice(0, shown).map((item, index) => (
            <li key={index}>
              <EvidenceValue
                value={item}
                api={api}
                workspaceId={workspaceId}
                revision={revision}
              />
            </li>
          ))}
        </ol>
        {shown < value.length && (
          <Button size="small" onPress={() => setShown((count) => count + 10)}>
            {t("evidence.moreValues", { remaining: value.length - shown })}
          </Button>
        )}
      </>
    );
  if (typeof value !== "object") return <span>{t("common.none")}</span>;
  const entries = Object.entries(value);
  const primary = entries.filter(([key]) => !technical.test(key));
  const metadata = entries.filter(([key]) => technical.test(key));
  const artifact = entries.find(
    ([key, item]) => key === "artifact_id" && typeof item === "string",
  )?.[1];
  const source = entries.find(
    ([key, item]) => key === "source_id" && typeof item === "string",
  )?.[1];
  const url =
    typeof artifact === "string"
      ? artifactLink(
          `/api/v1/artifacts/${encodeURIComponent(artifact)}/download`,
        )
      : undefined;
  return (
    <>
      {url && (
        <p>
          <Link href={url} download>
            {t("evidence.downloadSaved")}
          </Link>
        </p>
      )}
      {typeof source === "string" && (
        <SourceEvidence
          api={api}
          sourceId={source}
          workspaceId={workspaceId}
          revision={revision}
        />
      )}
      <dl className="evidence-value">
        {primary.slice(0, shown).map(([key, item]) => (
          <div key={key}>
            <dt>{fieldName(key)}</dt>
            <dd>
              <EvidenceValue
                value={item}
                api={api}
                workspaceId={workspaceId}
                revision={revision}
              />
            </dd>
          </div>
        ))}
      </dl>
      {shown < primary.length && (
        <Button size="small" onPress={() => setShown((count) => count + 10)}>
          {t("evidence.moreValues", { remaining: primary.length - shown })}
        </Button>
      )}
      {metadata.length > 0 && (
        <Disclosure title={t("common.details")}>
          <dl>
            {metadata.map(([key, item]) => (
              <div key={key}>
                <dt>{fieldName(key)}</dt>
                <dd>
                  <EvidenceValue
                    value={item}
                    api={api}
                    workspaceId={workspaceId}
                    revision={revision}
                  />
                </dd>
              </div>
            ))}
          </dl>
        </Disclosure>
      )}
    </>
  );
}
function answerTitle(answer: EvidenceAnswer) {
  if (answer.meaning === "profile.timeline") return t("evidence.timeline");
  if (answer.meaning === "profile.selected_resumes")
    return t("evidence.masterResumes");
  if (answer.meaning === "Imported role context")
    return t("evidence.caseContext");
  if (answer.meaning === "profile.current_bindings")
    return t("evidence.currentBindings");
  if (answer.meaning.startsWith("packet.upload_references."))
    return t("evidence.savedAttachments");
  if (answer.meaning.startsWith("packet.imported_review."))
    return t("evidence.savedReview");
  if (answer.meaning.startsWith("clarification."))
    return t("evidence.clarification");
  if (answer.meaning.startsWith("claim.")) return t("evidence.metricQuestion");
  if (
    answer.meaning.startsWith("case.") ||
    answer.meaning.startsWith("private.role")
  )
    return t("evidence.caseContext");
  return words(answer.meaning.replace(/\s+\[[a-f0-9]{8}\]$/i, ""));
}
function Answer({
  answer,
  api,
  workspaceId,
  revision,
  caseId,
}: {
  answer: EvidenceAnswer;
  api: Api;
  workspaceId: string;
  revision: number;
  caseId?: string;
}) {
  const disposition = [
    "answered",
    "pending",
    "unknown",
    "confidential",
    "declined",
  ].includes(answer.disposition)
    ? answer.disposition
    : "saved";
  const scoped = Object.keys(answer.scope).length > 0;
  return (
    <article className="evidence-record">
      <h3>{answerTitle(answer)}</h3>
      <div className="tags">
        <span className="tag">{t(`evidence.disposition.${disposition}`)}</span>
        <span className="tag">{t("common.private")}</span>
      </div>
      {answer.response_state === "pending" && (
        <p>{t("evidence.pendingHint")}</p>
      )}
      {answer.value !== null && (
        <EvidenceValue
          value={answer.value}
          api={api}
          workspaceId={workspaceId}
          revision={revision}
        />
      )}
      <p>
        {t(
          caseId
            ? answer.value_reusable_here
              ? "evidence.reusable"
              : "evidence.notReusable"
            : scoped
              ? "evidence.scopedHint"
              : "evidence.globalHint",
        )}
      </p>
      {Boolean(answer.scope.case_id) && <p>{t("evidence.caseScoped")}</p>}
      {Boolean(answer.scope.company_id) && <p>{t("evidence.companyScoped")}</p>}
      {Boolean(answer.scope.track_id || answer.scope.track_ids) && (
        <p>{t("evidence.trackScoped")}</p>
      )}
      {Object.keys(answer.units).length > 0 && (
        <section>
          <h4>{t("evidence.units")}</h4>
          <EvidenceValue
            value={answer.units}
            api={api}
            workspaceId={workspaceId}
            revision={revision}
          />
        </section>
      )}
      {scoped && (
        <Disclosure title={t("evidence.scope")}>
          <EvidenceValue
            value={answer.scope}
            api={api}
            workspaceId={workspaceId}
            revision={revision}
          />
        </Disclosure>
      )}
      {answer.evidence && (
        <Disclosure title={t("evidence.supportingNote")}>
          <EvidenceValue
            value={parsedEvidence(answer.evidence)}
            api={api}
            workspaceId={workspaceId}
            revision={revision}
          />
        </Disclosure>
      )}
      {!answer.valid_now && <p>{t("evidence.outdatedAnswer")}</p>}
      {answer.scope_unresolved && <p>{t("evidence.unresolvedScope")}</p>}
      {(answer.valid_from || answer.valid_until) && (
        <p>
          {answer.valid_from ? date(answer.valid_from) : t("common.none")} —{" "}
          {answer.valid_until ? date(answer.valid_until) : t("common.none")}
        </p>
      )}
      <Disclosure title={t("common.details")}>
        <p>{answer.meaning}</p>
        <p>{answer.id}</p>
      </Disclosure>
    </article>
  );
}
function Claim({
  claim,
  api,
  workspaceId,
  revision,
}: {
  claim: EvidenceClaim;
  api: Api;
  workspaceId: string;
  revision: number;
}) {
  return (
    <article className="evidence-record">
      <h3>{claim.assertion}</h3>
      <p>{claim.meaning}</p>
      <div className="tags">
        <span className="tag">
          {t(
            ["confirmed", "unknown", "hypothesis"].includes(claim.confirmation)
              ? `evidence.confirmation.${claim.confirmation}`
              : "evidence.confirmation.saved",
          )}
        </span>
        <span className="tag">
          {t(
            claim.disclosure === "allowed"
              ? "evidence.disclosure.allowed"
              : "evidence.disclosure.private",
          )}
        </span>
      </div>
      {Boolean(claim.contradicted) && <p>{t("evidence.contradicted")}</p>}
      {claim.source_ids.map((id, index) => (
        <SourceEvidence
          key={id}
          api={api}
          sourceId={id}
          workspaceId={workspaceId}
          revision={revision}
          label={t("evidence.numberedSource", { number: index + 1 })}
        />
      ))}
      {claim.detail && Object.keys(claim.detail).length > 0 && (
        <Disclosure title={t("evidence.supportingNote")}>
          <EvidenceValue
            value={claim.detail}
            api={api}
            workspaceId={workspaceId}
            revision={revision}
          />
        </Disclosure>
      )}
      <Disclosure title={t("common.details")}>
        <p>{claim.id}</p>
      </Disclosure>
    </article>
  );
}
export function EvidenceBank({
  api,
  workspaceId,
  revision,
  caseId,
  onAgent,
}: {
  api: Api;
  workspaceId: string;
  revision: number;
  caseId?: string;
  onAgent?: () => void;
}) {
  const [page, setPage] = useState<EvidenceContext>();
  const [failure, setFailure] = useState<Error>();
  const [pending, setPending] = useState(false);
  const [retry, setRetry] = useState(0);
  const [tab, setTab] = useState("claims");
  const generation = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const request = ++generation.current;
    const controller = new AbortController();
    setPage(undefined);
    setFailure(undefined);
    setPending(true);
    void load(undefined, controller.signal)
      .then((value) => {
        if (request === generation.current && !controller.signal.aborted)
          setPage(value);
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
  }, [api, workspaceId, revision, caseId, retry]);
  async function load(cursor?: string, signal?: AbortSignal) {
    const result = await api.request<EvidenceContext>(
      "/api/v1/context?" +
        new URLSearchParams({
          task: caseId ? "packets" : "profile",
          limit: "25",
          ...(caseId ? { case_id: caseId } : {}),
          ...(cursor ? { cursor } : {}),
        }),
      { signal },
    );
    if (
      result.workspace_id !== workspaceId ||
      result.revision !== revision ||
      !result.evidence
    )
      throw new Error("Evidence snapshot changed.");
    return result;
  }
  async function more() {
    if (!page?.next_cursor || pending) return;
    const request = generation.current;
    const returnFocus = document.activeElement === moreButton.current;
    setPending(true);
    setFailure(undefined);
    try {
      const value = await load(page.next_cursor);
      if (request === generation.current) {
        setPage({
          ...value,
          tracks: [...(page.tracks ?? []), ...(value.tracks ?? [])],
          evidence: {
            claims: [
              ...(page.evidence?.claims ?? []),
              ...value.evidence!.claims,
            ],
            answers: [
              ...(page.evidence?.answers ?? []),
              ...value.evidence!.answers,
            ],
            sources: [
              ...(page.evidence?.sources ?? []),
              ...value.evidence!.sources,
            ],
          },
        });
        if (!value.next_cursor && returnFocus)
          requestAnimationFrame(() => heading.current?.focus());
      }
    } catch (error) {
      if (request === generation.current) setFailure(error as Error);
    } finally {
      if (request === generation.current) setPending(false);
    }
  }
  const items = page?.evidence;
  const counts = {
    claims: items?.claims.length ?? 0,
    answers: items?.answers.length ?? 0,
    sources: items?.sources.length ?? 0,
  };
  return (
    <section
      className="evidence-bank"
      aria-label={t(caseId ? "evidence.caseContext" : "evidence.title")}
    >
      <div className="section-heading">
        <h2 ref={heading} tabIndex={-1}>
          {t(caseId ? "evidence.caseContext" : "evidence.title")}
        </h2>
        {onAgent && (
          <Button onPress={onAgent}>{t("evidence.withAgent")}</Button>
        )}
      </div>
      <p>{t("evidence.privateHint")}</p>
      {failure && (
        <Notice error>
          {errorText(failure)}{" "}
          <Button onPress={() => setRetry((value) => value + 1)}>
            {t("common.retry")}
          </Button>
        </Notice>
      )}
      {pending && !page && <p role="status">{t("common.loading")}</p>}
      {page && (
        <>
          <Tabs
            selectedKey={tab}
            onSelectionChange={(key) => setTab(String(key))}
          >
            <TabList aria-label={t("evidence.sections")}>
              <Tab id="claims">{t("evidence.claims")}</Tab>
              <Tab id="answers">{t("evidence.answers")}</Tab>
              <Tab id="sources">{t("evidence.sources")}</Tab>
            </TabList>
            <TabPanel id="claims">
              <p>
                {t("evidence.loaded", {
                  loaded: counts.claims,
                  total: page.pagination?.claims?.total ?? counts.claims,
                })}
              </p>
              {items?.claims.map((claim) => (
                <Claim
                  key={claim.id}
                  claim={claim}
                  api={api}
                  workspaceId={workspaceId}
                  revision={page.revision}
                />
              ))}
              {!counts.claims && <p>{t("evidence.emptyClaims")}</p>}
            </TabPanel>
            <TabPanel id="answers">
              <p>
                {t("evidence.loaded", {
                  loaded: counts.answers,
                  total: page.pagination?.answers?.total ?? counts.answers,
                })}
              </p>
              {items?.answers.map((answer) => (
                <Answer
                  key={answer.id}
                  answer={answer}
                  api={api}
                  workspaceId={workspaceId}
                  revision={page.revision}
                  caseId={caseId}
                />
              ))}
              {!counts.answers && <p>{t("evidence.emptyAnswers")}</p>}
            </TabPanel>
            <TabPanel id="sources">
              <p>
                {t("evidence.loaded", {
                  loaded: counts.sources,
                  total: page.pagination?.sources?.total ?? counts.sources,
                })}
              </p>
              {items?.sources.map((source) => (
                <SourceEvidence
                  key={source.id}
                  api={api}
                  sourceId={source.id}
                  source={source}
                  workspaceId={workspaceId}
                  revision={page.revision}
                />
              ))}
              {!counts.sources && <p>{t("evidence.emptySources")}</p>}
            </TabPanel>
          </Tabs>
          {page.partial && <p className="help">{t("evidence.partialHint")}</p>}
          {page.next_cursor && (
            <Button
              ref={moreButton}
              isDisabled={pending}
              onPress={() => void more()}
            >
              {pending ? t("common.loading") : t("evidence.more")}
            </Button>
          )}
        </>
      )}
    </section>
  );
}
