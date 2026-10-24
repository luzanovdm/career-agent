import { t, issueText, errorText, date } from "../app/i18n";
import { useState, useEffect, useRef } from "react";
import { Tabs, TabList, Tab, TabPanel } from "../ui/controls";
import type { Api } from "../api/client";
import { artifactLink, safeLink } from "../api/client";
import type {
  Action,
  ActivityKind,
  CaseDetail,
  Receipt,
  AgentIntent,
} from "../api/types";
import {
  DialogSurface,
  Hint,
  Link,
  Disclosure,
  Button,
  Choice,
  Field,
  Notice,
} from "../ui/controls";
import {
  SaveButtons,
  SaveState,
  useDraft,
  useEditorMode,
  type Dirty,
} from "./editing";
import { AgentPrompt } from "./AgentPrompt";
export function Detail({
  detail,
  api,
  onDirty,
  refresh,
  onPacket,
  materialLanguage,
}: {
  detail: CaseDetail;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
  onPacket: (id: string) => void;
  materialLanguage?: string;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  // The lazy view owns its first mounted focus; revision refreshes preserve edit focus.
  useEffect(() => {
    heading.current?.focus();
  }, [detail.case.id]);
  const [tab, setTab] = useState("materials"),
    [action, setAction] = useState<Action>(),
    [handoff, setHandoff] = useState<{
      intent: AgentIntent;
      instruction?: string;
    }>();
  const selection = detail.selection;
  const preferredIntent: AgentIntent =
    detail.case.column === "qualify"
      ? "agent.research"
      : detail.case.column === "prepare"
        ? "agent.prepare"
        : "agent.review";
  const primary =
    detail.case.allowed_actions.find(
      (action) => action.intent === preferredIntent,
    ) ??
    detail.case.allowed_actions.find((action) =>
      action.intent.startsWith("agent."),
    );
  const openAgent = (intent: AgentIntent, instruction?: string) =>
    setHandoff({ intent, instruction });
  return (
    <>
      <div className="page-heading detail-heading">
        <div className="detail-identity">
          <p className="company-name">{detail.case.company}</p>
          <h1 ref={heading} tabIndex={-1}>
            {detail.case.title}
          </h1>
          <div className="tags">
            {detail.case.tracks.map((track) => (
              <Hint text={track.rationale} key={track.id}>
                {track.name}
              </Hint>
            ))}
            <span className="tag">{t(`cases.${detail.case.kind}`)}</span>
          </div>
        </div>
        {primary && (
          <Button
            variant="primary"
            className="agent-entry"
            onPress={() =>
              openAgent(
                primary.intent as AgentIntent,
                detail.case.column === "waiting" ||
                  detail.case.column === "response"
                  ? t("agent.reconcileInstruction")
                  : undefined,
              )
            }
          >
            {t(`primary.${detail.case.column}`)}
          </Button>
        )}
      </div>
      <div className="case-context">
        <span>
          <strong>
            {detail.case.contact?.name ?? t("cases.contactMissing")}
          </strong>{" "}
          ·{" "}
          {t(
            detail.case.route === "person"
              ? "cases.routePerson"
              : detail.case.route === "form"
                ? "cases.routeForm"
                : "cases.routeUnknown",
          )}
        </span>
        <span>{t(`column.${detail.case.column}`)}</span>
      </div>
      {detail.case.contact?.relevance && (
        <p className="contact-relevance">{detail.case.contact.relevance}</p>
      )}
      {detail.case.contact?.route &&
        safeLink(detail.case.contact.route.value) && (
          <p className="professional-route">
            <Link
              href={safeLink(detail.case.contact.route.value)}
              target="_blank"
              rel="noopener noreferrer"
              referrerPolicy="no-referrer"
            >
              {detail.case.contact.route.value}
            </Link>{" "}
            ·{" "}
            {t(
              detail.case.contact.qualified
                ? "detail.qualified"
                : "detail.qualificationPending",
            )}
          </p>
        )}
      <div className="detail-layout">
        <section className="editor-pane">
          <div className="packet-heading">
            <div>
              <h2>{t("detail.selectedMaterials")}</h2>
              <p>{selection ? t("detail.editHint") : t("detail.noPacket")}</p>
            </div>
          </div>
          {selection && (
            <div className="assessment">
              <span className="material-status">
                {t(
                  selection.assessment.prepared
                    ? "detail.reviewed"
                    : "detail.needsReview",
                )}
              </span>
            </div>
          )}
          <Tabs
            selectedKey={tab}
            onSelectionChange={(key) => setTab(String(key))}
          >
            <TabList aria-label={t("nav.caseDetail")}>
              <Tab id="materials">{t("detail.materials")}</Tab>
              <Tab id="interview">{t("detail.preparation")}</Tab>
              <Tab id="history">{t("detail.history")}</Tab>
            </TabList>
            <TabPanel id="materials" shouldForceMount>
              <Materials
                materialLanguage={materialLanguage}
                key={selection?.packet_id ?? "none"}
                detail={detail}
                api={api}
                onDirty={onDirty}
                refresh={refresh}
                onAgent={() =>
                  openAgent("agent.prepare", t("agent.rewriteInstruction"))
                }
              />
            </TabPanel>
            <TabPanel id="interview" shouldForceMount>
              <Interview detail={detail} materialLanguage={materialLanguage} />
              <Button
                onPress={() =>
                  openAgent("agent.prepare", t("detail.prepEmptyHint"))
                }
              >
                {t("agent.interview")}
              </Button>
            </TabPanel>
            <TabPanel id="history" shouldForceMount>
              <History detail={detail} />
              <Button
                onPress={() =>
                  openAgent("agent.review", t("agent.reconcileInstruction"))
                }
              >
                {t("agent.reconcile")}
              </Button>
            </TabPanel>
          </Tabs>
        </section>
        <aside className="detail-aside" aria-label={t("detail.privateWork")}>
          <section className="panel next-panel">
            <h2>{t("cases.nextAction")}</h2>
            <p>{t(`next.${detail.case.column}`)}</p>
            {detail.case.blockers.map((issue, index) => (
              <p key={index} className="blocker">
                {issueText(issue)}
              </p>
            ))}
            <div className="action-list">
              {detail.case.allowed_actions
                .filter(
                  (item) =>
                    item.intent === "agent.prepare" ||
                    item.intent === "agent.review",
                )
                .map((item) => (
                  <Button
                    key={item.intent}
                    onPress={() => openAgent(item.intent as AgentIntent)}
                  >
                    {t(item.intent)}
                  </Button>
                ))}
              <Button
                onPress={() =>
                  openAgent("agent.review", t("agent.reconcileInstruction"))
                }
              >
                {t("agent.reconcile")}
              </Button>
            </div>
          </section>
          <PrivateNotes
            detail={detail}
            api={api}
            onDirty={onDirty}
            refresh={refresh}
          />
          <Disclosure className="case-record" title={t("common.details")}>
            <dl>
              <dt>{t("nav.caseDetail")}</dt>
              <dd>{detail.case.id}</dd>
              <dt>{t("cases.vacancy")}</dt>
              <dd>{detail.case.opportunity_id ?? t("detail.noOpportunity")}</dd>
            </dl>
            {detail.case.allowed_actions
              .filter((item) =>
                ["case.close", "case.reopen"].includes(item.intent),
              )
              .map((item) => (
                <Button key={item.intent} onPress={() => setAction(item)}>
                  {t(
                    item.intent === "case.close"
                      ? "action.close"
                      : "action.reopen",
                  )}
                </Button>
              ))}
          </Disclosure>
        </aside>
      </div>
      {action && (
        <ActionDialog
          action={action}
          detail={detail}
          api={api}
          onClose={() => setAction(undefined)}
          refresh={refresh}
        />
      )}{" "}
      {handoff && (
        <AgentPrompt
          api={api}
          workspaceId={detail.workspace_id}
          revision={detail.revision}
          caseId={detail.case.id}
          scopeLabel={`${detail.case.company} · ${detail.case.title}`}
          tracks={detail.case.tracks}
          intent={handoff.intent}
          instruction={handoff.instruction}
          onClose={() => setHandoff(undefined)}
        />
      )}
    </>
  );
}
function Materials({
  detail,
  api,
  onDirty,
  refresh,
  onAgent,
  materialLanguage,
}: {
  detail: CaseDetail;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
  onAgent: () => void;
  materialLanguage?: string;
}) {
  const selection = detail.selection,
    initial = Object.fromEntries(
      (selection?.slots ?? [])
        .filter((slot) => slot.text !== null)
        .map((slot) => [slot.name, slot.text!]),
    );
  const draft = useDraft(
    `packet-${selection?.packet_id ?? detail.case.id}`,
    initial,
    detail.revision,
    onDirty,
  );
  const [active, setActive] = useState(
    initial.message !== undefined
      ? "message"
      : initial.resume !== undefined
        ? "resume"
        : (Object.keys(initial)[0] ?? ""),
  );
  const { editing, setEditing, editTrigger, cancelEditing } = useEditorMode();
  const names = Object.keys(initial),
    current = names.includes(active) ? active : names[0],
    slot = selection?.slots.find((item) => item.name === current);
  useEffect(() => {
    if (draft.receipt && !draft.dirty && !draft.pending) setEditing(false);
  }, [draft.receipt, draft.dirty, draft.pending]);
  const save = () => {
    if (!selection) return;
    void draft
      .save((value, revision) =>
        api.command(
          "packet.save",
          {
            packet_id: selection.packet_id,
            documents: Object.entries(value).map(([slot, text]) => ({
              slot,
              text,
            })),
            used_claim_ids: selection.used_claim_ids ?? [],
            answer_ids: selection.answer_ids ?? [],
            source_version_id: selection.version_id,
          },
          revision,
        ),
      )
      .then((result) => result && refresh(result.revision));
  };
  if (!selection)
    return (
      <div className="empty-state">
        <h3>{t("detail.noPacket")}</h3>
        <p>{t("detail.noPacketHint")}</p>
        <Button variant="primary" onPress={onAgent}>
          {t("agent.prepare")}
        </Button>
      </div>
    );
  return (
    <div className="material-content" id="material-editor" tabIndex={-1}>
      <div className="material-toolbar">
        <Choice
          label={t("detail.document")}
          value={current ?? ""}
          onChange={setActive}
          options={names.map((name) => ({
            id: name,
            name: ["dossier", "interview", "notes"].includes(name)
              ? t("detail.documentPrivate", { document: t(`slot.${name}`) })
              : t(`slot.${name}`),
          }))}
        />
        {!editing && names.length > 0 && (
          <Button
            ref={editTrigger}
            size="small"
            onPress={() => {
              setEditing(true);
              requestAnimationFrame(() =>
                document.getElementById("document-draft")?.focus(),
              );
            }}
          >
            {t("detail.edit")}
          </Button>
        )}
        <Button
          size="small"
          isDisabled={draft.dirty || draft.pending}
          onPress={onAgent}
        >
          {t("detail.improve")}
        </Button>
      </div>
      {editing && (
        <>
          <p className="help">{t("detail.editHint")}</p>
          <SaveButtons
            dirty={draft.dirty}
            pending={draft.pending}
            onSave={save}
            onCancel={() => {
              draft.cancel();
              cancelEditing();
            }}
          />
        </>
      )}
      <SaveState
        draft={draft}
        latest={<pre lang={materialLanguage}>{initial[current] ?? ""}</pre>}
      />
      {editing ? (
        <Field
          inputId="document-draft"
          contentLanguage={materialLanguage}
          label={t("detail.documentDraft", { document: t(`slot.${current}`) })}
          multiline
          value={draft.value[current] ?? ""}
          onChange={(text) =>
            draft.setValue({ ...draft.value, [current]: text })
          }
        />
      ) : (
        <article className="document-preview" aria-label={t("detail.reading")}>
          <p className="document-title">
            {t(`slot.${current}`)}
            {["dossier", "interview", "notes"].includes(current)
              ? " · " + t("common.private")
              : ""}
          </p>
          <pre lang={materialLanguage}>{initial[current] ?? ""}</pre>
        </article>
      )}
      {(selection.assessment.issues.length > 0 ||
        selection.assessment.unknowns.length > 0) && (
        <Disclosure className="review-details" title={t("detail.needsReview")}>
          {selection.assessment.issues.map((issue, index) => (
            <p key={index}>{issueText(issue)}</p>
          ))}
          <ul>
            {selection.assessment.unknowns.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        </Disclosure>
      )}
      <Disclosure className="document-record" title={t("detail.version")}>
        <p className="document-meta">
          {selection.version_id}
          <br />
          {slot?.sha256 ? "SHA-256 " + slot.sha256 : ""}
        </p>
      </Disclosure>
      {draft.dirty && <p className="help">{t("detail.downloadHint")}</p>}
      <ul className="downloads">
        {selection.slots.map((item) => {
          const url = artifactLink(item.download_url);
          return (
            <li key={item.artifact_id}>
              {url ? (
                <Link href={url} download>
                  {t("detail.download", { document: t(`slot.${item.name}`) })}
                </Link>
              ) : (
                <span>
                  {t("detail.downloadUnavailable", {
                    document: t(`slot.${item.name}`),
                  })}
                </span>
              )}
              {["dossier", "interview", "notes"].includes(item.name) && (
                <span className="tag">{t("common.private")}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
function PrivateNotes({
  detail,
  api,
  onDirty,
  refresh,
}: {
  detail: CaseDetail;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
}) {
  const draft = useDraft(
    `notes-${detail.case.id}`,
    detail.notes,
    detail.revision,
    onDirty,
  );
  return (
    <section className="panel" id="private-notes" tabIndex={-1}>
      <h2>{t("detail.notes")}</h2>
      <Field
        label={t("detail.notesLabel")}
        multiline
        value={draft.value}
        onChange={draft.setValue}
        description={t("detail.notesHint")}
      />
      <SaveState draft={draft} latest={<pre>{detail.notes}</pre>} />
      <SaveButtons
        dirty={draft.dirty}
        pending={draft.pending}
        onCancel={draft.cancel}
        onSave={() =>
          void draft
            .save((text, revision) =>
              api.command(
                "case.note",
                { case_id: detail.case.id, text },
                revision,
              ),
            )
            .then((r) => r && refresh(r.revision))
        }
      />
    </section>
  );
}
function Interview({
  detail,
  materialLanguage,
}: {
  detail: CaseDetail;
  materialLanguage?: string;
}) {
  return (
    <div className="interview">
      <p className="help">{t("detail.prepHint")}</p>
      {detail.interview.length === 0 ? (
        <div className="empty-state">
          <h3>{t("detail.prepEmpty")}</h3>
          <p>{t("detail.prepEmptyHint")}</p>
        </div>
      ) : (
        <ol className="dialogue">
          {detail.interview.map((item, index) => (
            <li
              key={`${item.artifact_id}-${index}`}
              className={index % 2 ? "answer" : "prompt"}
            >
              <span className="bubble-label">
                {t(`slot.${item.slot}`)} · {t("detail.savedPrep")}
              </span>
              <p lang={materialLanguage}>{item.text}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
function History({ detail }: { detail: CaseDetail }) {
  return (
    <div className="history">
      <h3>{t("detail.activity")}</h3>
      {detail.history.length === 0 && <p>{t("detail.activityEmpty")}</p>}
      <ol>
        {detail.history.map((item) => (
          <li key={item.id}>
            <strong>{t(`activity.${item.kind}`)}</strong>{" "}
            <time dateTime={item.occurred_at}>{date(item.occurred_at)}</time>
            <p>{item.evidence}</p>
            {item.version_id && (
              <small>
                {t("detail.materialVersion", { version: item.version_id })}
              </small>
            )}
          </li>
        ))}
      </ol>
      <h3>{t("detail.sources")}</h3>
      {detail.sources.map((source) => (
        <section key={source.id}>
          <strong>{source.id}</strong>
          <p>
            {safeLink(source.locator) ? (
              <Link
                href={safeLink(source.locator)}
                target="_blank"
                rel="noopener noreferrer"
                referrerPolicy="no-referrer"
              >
                {source.locator}
              </Link>
            ) : (
              source.locator
            )}
          </p>
          <blockquote>{source.excerpt}</blockquote>
          <small>
            {date(source.observed_at)} ·{" "}
            {source.readable
              ? t("detail.sourceReadable")
              : t("detail.sourceUnknown")}
          </small>
        </section>
      ))}
    </div>
  );
}
function ActionDialog({
  action,
  detail,
  api,
  onClose,
  refresh,
}: {
  action: Action;
  detail: CaseDetail;
  api: Api;
  onClose: () => void;
  refresh: (revision: number) => void;
}) {
  const [reason, setReason] = useState(""),
    [pending, setPending] = useState(false),
    [error, setError] = useState("");
  async function apply() {
    setPending(true);
    setError("");
    try {
      const result =
        action.intent === "case.close"
          ? await api.command(
              "case.close",
              {
                case_id: detail.case.id,
                reason,
                evidence:
                  "User explicitly closed this case in the local interface: " +
                  reason,
              },
              detail.revision,
            )
          : await api.command(
              "case.reopen",
              { case_id: detail.case.id, reason },
              detail.revision,
            );
      refresh(result.revision);
      if (result.outcome === "satisfied") onClose();
      else setError(t("save.partial"));
    } catch (error) {
      setError(errorText(error as Error));
    } finally {
      setPending(false);
    }
  }
  return (
    <DialogSurface
      title={t(
        action.intent === "case.close" ? "action.close" : "action.reopen",
      )}
      onClose={() => !pending && onClose()}
    >
      <p>{t("action.closureHint")}</p>
      <Field
        label={t("action.reason")}
        value={reason}
        onChange={setReason}
        multiline
        required
      />
      {error && <Notice error>{error}</Notice>}
      <div className="actions">
        <Button isDisabled={pending} onPress={onClose}>
          {t("common.cancel")}
        </Button>
        <Button
          variant="primary"
          isDisabled={!reason.trim() || pending}
          onPress={() => void apply()}
        >
          {pending
            ? t("common.saving")
            : t(
                action.intent === "case.close"
                  ? "action.close"
                  : "action.reopen",
              )}
        </Button>
      </div>
    </DialogSurface>
  );
}
