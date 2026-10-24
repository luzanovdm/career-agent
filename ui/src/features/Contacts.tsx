import { t, issueText } from "../app/i18n";
import {
  Table,
  TableHeader,
  Column,
  TableBody,
  Row,
  Cell,
} from "../ui/controls";
import { useState } from "react";
import type { Contact, ContactPage, CommandInputs } from "../api/types";
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
}: {
  page?: ContactPage;
  onMore: () => void;
  pending: boolean;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
  navigate: (action: () => void) => void;
}) {
  const [selected, setSelected] = useState<string>();
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
          onRowAction={(key) => navigate(() => setSelected(String(key)))}
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
                    onPress={() => navigate(() => setSelected(item.id))}
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
              <strong>{source.source_id}</strong>
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
