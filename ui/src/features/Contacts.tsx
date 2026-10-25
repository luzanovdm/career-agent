import { t, issueText, errorText } from "../app/i18n";
import {
  Table,
  TableHeader,
  Column,
  TableBody,
  Row,
  Cell,
} from "../ui/controls";
import { useEffect, useRef, useState } from "react";
import type {
  Contact,
  ContactPage,
  CommandInputs,
  PacketPage,
} from "../api/types";
import { SourceEvidence } from "./SourceEvidence";
import { packetLabel } from "./PacketLabel";
import { safeLink, type Api } from "../api/client";
import { Link, Disclosure, Button, Choice, Field } from "../ui/controls";
import { SaveButtons, SaveState, useDraft, type Dirty } from "./editing";
export function Contacts({
  page,
  onMore,
  pending,
  api,
  onDirty,
  refresh,
  navigate,
  selected,
  onSelect,
  onOpenPacket,
}: {
  page?: ContactPage;
  onMore: () => void;
  pending: boolean;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
  navigate: (action: () => void) => void;
  selected?: string;
  onSelect: (id: string) => void;
  onOpenPacket: (caseId: string, packetId: string) => void;
}) {
  const contact = page?.items.find((item) => item.id === selected);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{t("contacts.title")}</h1>
          <p>
            {t("contacts.count", { count: page?.total ?? 0 })} ·{" "}
            {t("contacts.description")}
          </p>
        </div>
      </div>
      <div className="table-wrap">
        <Table
          aria-label={t("contacts.title")}
          onRowAction={(key) => navigate(() => onSelect(String(key)))}
        >
          <TableHeader>
            <Column isRowHeader>{t("contacts.name")}</Column>
            <Column>{t("contacts.company")}</Column>
            <Column>{t("contacts.route")}</Column>
            <Column>{t("contacts.qualification")}</Column>
          </TableHeader>
          <TableBody
            items={page?.items ?? []}
            renderEmptyState={() => t("contacts.empty")}
          >
            {(item) => (
              <Row id={item.id}>
                <Cell>
                  <Button
                    className="table-open"
                    onPress={() => navigate(() => onSelect(item.id))}
                  >
                    {item.name}
                  </Button>
                  <small>{item.relevance}</small>
                </Cell>
                <Cell>
                  {item.company ?? t("common.none")}
                  <small>{t(`affiliation.${item.affiliation}`)}</small>
                </Cell>
                <Cell>
                  {item.route && safeLink(item.route.value) ? (
                    <Link
                      href={safeLink(item.route.value)}
                      target="_blank"
                      rel="noopener noreferrer"
                      referrerPolicy="no-referrer"
                    >
                      {item.route.value}
                    </Link>
                  ) : (
                    t("contacts.noRoute")
                  )}
                </Cell>
                <Cell>
                  {item.qualified
                    ? t("detail.qualified")
                    : t("contacts.needsQualification")}
                  {item.issues.map((issue, i) => (
                    <small key={i}>{issueText(issue)}</small>
                  ))}
                </Cell>
              </Row>
            )}
          </TableBody>
        </Table>
        {page?.next_cursor && (
          <Button className="load-more" isDisabled={pending} onPress={onMore}>
            {t("contacts.more")}
          </Button>
        )}
      </div>
      {contact && (
        <ContactPackets
          key={contact.id}
          contact={contact}
          revision={page!.revision}
          workspaceId={page!.workspace_id}
          api={api}
          onOpen={onOpenPacket}
        />
      )}
      {contact && (
        <ContactEditor
          key={contact.id}
          contact={contact}
          revision={page!.revision}
          api={api}
          onDirty={onDirty}
          refresh={refresh}
        />
      )}
    </>
  );
}
function ContactEditor({
  contact,
  revision,
  api,
  onDirty,
  refresh,
}: {
  contact: Contact;
  revision: number;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
}) {
  const input: CommandInputs["contact.capture"] = {
    id: contact.id,
    name: contact.name,
    company_id: contact.company_id,
    affiliation: contact.affiliation,
    relevance: contact.relevance,
    sources: contact.sources,
    route: contact.route,
    ...(contact.relationship !== undefined
      ? { relationship: contact.relationship }
      : {}),
    ...(contact.valid_until !== undefined
      ? { valid_until: contact.valid_until }
      : {}),
  };
  const draft = useDraft(`contact-${contact.id}`, input, revision, onDirty);
  return (
    <section className="panel contact-editor">
      <h2>
        {t("common.edit")}
        {contact.name}
      </h2>
      <Field
        label={t("contacts.name")}
        value={draft.value.name}
        onChange={(name) => draft.setValue({ ...draft.value, name })}
      />
      <Field
        label={t("contacts.relevance")}
        value={draft.value.relevance}
        multiline
        onChange={(relevance) => draft.setValue({ ...draft.value, relevance })}
      />
      <Choice
        label={t("contacts.affiliation")}
        value={draft.value.affiliation}
        onChange={(affiliation) =>
          draft.setValue({
            ...draft.value,
            affiliation: affiliation as Contact["affiliation"],
          })
        }
        options={["current", "unknown", "conflicting", "former"].map((id) => ({
          id,
          name: t(`affiliation.${id}`),
        }))}
      />
      {draft.value.route && (
        <Field
          label={t("contacts.recordedRoute")}
          value={draft.value.route.value}
          onChange={(value) =>
            draft.setValue({
              ...draft.value,
              route: { ...draft.value.route!, value },
            })
          }
          description={t("contacts.routeSource", {
            source: draft.value.route.source_id,
          })}
        />
      )}
      <Disclosure title={t("contacts.sourceAssessments")}>
        <ul className="source-assessments">
          {contact.sources.map((source, index) => (
            <li key={index}>
              <SourceEvidence
                api={api}
                sourceId={source.source_id}
                revision={revision}
              />
              <p>
                {source.axes
                  .map((axis) =>
                    t(
                      axis === "affiliation"
                        ? "contacts.affiliationAxis"
                        : axis === "relevance"
                          ? "contacts.relevanceAxis"
                          : "contacts.identity",
                    ),
                  )
                  .join(", ")}{" "}
                · {t(`contacts.${source.assessment}`)}
              </p>
            </li>
          ))}
        </ul>
      </Disclosure>
      <p className="help">{t("contacts.runtimeHint")}</p>
      <SaveState
        draft={draft}
        latest={<pre>{JSON.stringify(input, null, 2)}</pre>}
      />
      <SaveButtons
        dirty={draft.dirty}
        pending={draft.pending}
        onCancel={draft.cancel}
        onSave={() =>
          void draft
            .save((value, base) => api.command("contact.capture", value, base))
            .then((r) => r && refresh(r.revision))
        }
      />
    </section>
  );
}

function ContactPackets({
  contact,
  revision,
  workspaceId,
  api,
  onOpen,
}: {
  contact: Contact;
  revision: number;
  workspaceId: string;
  api: Api;
  onOpen: (caseId: string, packetId: string) => void;
}) {
  const [page, setPage] = useState<PacketPage>();
  const [failure, setFailure] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    generation.current++;
    setPage(undefined);
    setFailure("");
    setLoading(true);
    void api
      .contactPackets(contact.id, undefined, controller.signal)
      .then((result) => {
        if (result.workspace_id !== workspaceId || result.revision !== revision)
          throw new Error("Snapshot changed; refresh contacts.");
        if (!controller.signal.aborted) setPage(result);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setFailure(errorText(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      generation.current++;
    };
  }, [api, contact.id, revision, workspaceId, retry]);
  async function more() {
    if (!page?.next_cursor || loading) return;
    const request = generation.current;
    setLoading(true);
    setFailure("");
    try {
      const result = await api.contactPackets(contact.id, page.next_cursor);
      if (
        result.workspace_id !== page.workspace_id ||
        result.revision !== page.revision
      )
        throw new Error("Snapshot changed; refresh contacts.");
      if (request === generation.current)
        setPage({ ...result, items: [...page.items, ...result.items] });
    } catch (error) {
      if (request === generation.current) setFailure(errorText(error as Error));
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }
  return (
    <section
      className="panel contact-packets"
      aria-label={t("packet.forPerson", { name: contact.name })}
    >
      <h2>{t("packet.forPerson", { name: contact.name })}</h2>
      {loading && <p role="status">{t("common.loading")}</p>}
      {failure && (
        <div role="alert">
          {failure}
          <Button onPress={() => setRetry((n) => n + 1)}>
            {t("common.retry")}
          </Button>
        </div>
      )}
      {page && page.total === 0 && <p>{t("packet.none")}</p>}
      <ul>
        {page?.items.map((packet) => (
          <li key={packet.id}>
            <Button
              onPress={() =>
                packet.case_id && onOpen(packet.case_id, packet.id)
              }
            >
              {packetLabel(packet)}
            </Button>
            <p>
              {packet.company} · {packet.case_title}
            </p>
          </li>
        ))}
      </ul>
      {page?.next_cursor && (
        <Button onPress={() => void more()} isDisabled={loading}>
          {t("packet.more")}
        </Button>
      )}
    </section>
  );
}
