import { Fragment, type ReactNode } from "react";
import { safeLink } from "../api/client";
import { t, date } from "../app/i18n";
import { Button, Disclosure, Link } from "../ui/controls";
export interface InterviewSource {
  id: string;
  locator: string | null;
  observed_at: string | null;
  readable: boolean;
  available: boolean;
}
export interface InterviewTerm {
  label: string;
  url: string;
  source_id: string;
  available: boolean;
  limitation: string | null;
}
export interface InterviewItem {
  slot: string;
  artifact_id: string;
  text: string | null;
  kind?: "question" | "answer" | "note" | "document" | "file";
  status?: "outline" | "confirmed" | "unknown" | "hypothesis" | null;
  sources?: InterviewSource[];
  terms?: InterviewTerm[];
}
function SavedBody({
  item,
  language,
}: {
  item: InterviewItem;
  language?: string;
}) {
  const text = item.text ?? "";
  const terms = (item.terms ?? []).filter(
    (term) => term.available && safeLink(term.url),
  );
  const parts: ReactNode[] = [];
  const used = new Set<string>();
  let start = 0;
  while (start < text.length) {
    let found: InterviewTerm | undefined;
    let position = text.length;
    for (const term of terms) {
      // One inline link per declared term keeps repeated technical text bounded.
      if (used.has(term.label)) continue;
      const candidate = text.indexOf(term.label, start);
      if (candidate >= 0 && candidate < position) {
        found = term;
        position = candidate;
      }
    }
    if (!found) {
      parts.push(text.slice(start));
      break;
    }
    parts.push(text.slice(start, position));
    parts.push(
      <Link
        key={`${position}-${found.source_id}`}
        href={safeLink(found.url)}
        target="_blank"
        rel="noopener noreferrer"
        referrerPolicy="no-referrer"
      >
        {found.label}
      </Link>,
    );
    used.add(found.label);
    start = position + found.label.length;
  }
  return (
    <>
      <p lang={language}>
        {parts.map((part, index) => (
          <Fragment key={index}>{part}</Fragment>
        ))}
      </p>
      {(item.terms ?? []).some(
        (term) => !term.available || !used.has(term.label),
      ) && (
        <div className="interview-terms">
          {(item.terms ?? [])
            .filter((term) => !term.available || !used.has(term.label))
            .map((term) => (
              <p key={`${term.source_id}-${term.label}`}>
                {term.available && safeLink(term.url) ? (
                  <Link
                    href={safeLink(term.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    referrerPolicy="no-referrer"
                  >
                    {term.label}
                  </Link>
                ) : (
                  <span>
                    {term.label} · {t("interview.referenceUnavailable")}
                  </span>
                )}
              </p>
            ))}
        </div>
      )}
    </>
  );
}
export function Interview({
  detail,
  materialLanguage,
  onMaterials,
}: {
  detail: { interview: InterviewItem[] };
  materialLanguage?: string;
  onMaterials: () => void;
}) {
  // Older plain documents remain documents. Array position never supplies a role.
  const items: InterviewItem[] = detail.interview;
  return (
    <div className="interview">
      <p className="help">{t("detail.prepHint")}</p>
      {items.length === 0 ? (
        <div className="empty-state">
          <h3>{t("detail.prepEmpty")}</h3>
          <p>{t("detail.prepEmptyHint")}</p>
        </div>
      ) : (
        <ol className="dialogue" aria-label={t("interview.savedSequence")}>
          {items.map((item, index) => {
            const kind =
              item.kind ?? (item.text === null ? "file" : "document");
            return (
              <li
                key={`${item.artifact_id}-${index}`}
                className={
                  kind === "answer"
                    ? "answer"
                    : kind === "question"
                      ? "question"
                      : "note"
                }
              >
                <span className="bubble-label">
                  {t(`interview.${kind}`)}
                  {item.status
                    ? ` · ${t(`interview.status.${item.status}`)}`
                    : ""}
                </span>
                {kind === "file" ? (
                  <>
                    <p>{t("interview.fileOnly")}</p>
                    <Button onPress={onMaterials}>
                      {t("detail.materials")}
                    </Button>
                  </>
                ) : (
                  <SavedBody item={item} language={materialLanguage} />
                )}
                {!!item.sources?.length && (
                  <Disclosure title={t("interview.sources")}>
                    <div>
                      {item.sources.map((source) => (
                        <div key={source.id}>
                          {source.available &&
                          source.locator &&
                          safeLink(source.locator) ? (
                            <Link
                              href={safeLink(source.locator)}
                              target="_blank"
                              rel="noopener noreferrer"
                              referrerPolicy="no-referrer"
                            >
                              {source.locator}
                            </Link>
                          ) : (
                            <span>{t("interview.referenceUnavailable")}</span>
                          )}
                          {source.observed_at && (
                            <p>
                              <time dateTime={source.observed_at}>
                                {date(source.observed_at)}
                              </time>
                            </p>
                          )}
                          <small>{source.id}</small>
                        </div>
                      ))}
                    </div>
                  </Disclosure>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
