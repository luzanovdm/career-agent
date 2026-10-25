import { date, t } from "../app/i18n";
import { Disclosure, Link } from "../ui/controls";

export interface ExportView {
  kind: "csv" | "xlsx" | "profile" | "snapshot";
  revision: number | null;
  status: "current" | "stale" | "missing";
  generated_at?: string | null;
  files?: readonly { name: string; download_url: string }[];
  issue?: string;
}

/** Only the server's opaque manifest-bound export route can become a download. */
export function safeExportLink(value: string): string | undefined {
  if (!/^\/api\/v1\/exports\/[A-Za-z0-9_-]+\/files\/\d+$/u.test(value))
    return undefined;
  const origin = globalThis.location?.origin ?? "http://local.invalid";
  const resolved = new URL(value, origin);
  return resolved.origin === origin ? value : undefined;
}

/** Derived files are read-only snapshots; opening this list performs no command. */
export function Exports({
  exports,
  revision,
}: {
  exports?: readonly ExportView[];
  revision: number;
}) {
  const views = exports ?? [];
  const stale = views.some((view) => view.status === "stale");
  return (
    <Disclosure
      title={t(stale ? "exports.stale" : "exports.title")}
      className={`exports-panel ${stale ? "stale-banner" : ""}`}
    >
      <p>{t("exports.explanation", { revision })}</p>
      <p className="help">{t("exports.refreshHint")}</p>
      {views.length === 0 ? (
        <p>{t("exports.none")}</p>
      ) : (
        <ul className="export-list">
          {views.map((view) => (
            <li key={view.kind}>
              <h3>{t(`exports.${view.kind}`)}</h3>
              <p>
                {view.status === "missing" || view.revision === null
                  ? t("exports.missing")
                  : t(
                      view.status === "stale"
                        ? "exports.staleStatus"
                        : "exports.current",
                      { revision: view.revision },
                    )}
              </p>
              {view.generated_at ? (
                <p>
                  {t("exports.generated")}{" "}
                  <time dateTime={view.generated_at}>
                    {date(view.generated_at)}
                  </time>
                </p>
              ) : (
                view.status !== "missing" && (
                  <p className="help">{t("exports.dateUnknown")}</p>
                )
              )}
              {view.issue && <p className="help">{t("exports.unavailable")}</p>}
              {(view.files?.length ?? 0) > 0 && (
                <ul className="downloads">
                  {view.files!.map((file, index) => {
                    const url = safeExportLink(file.download_url);
                    return (
                      <li key={`${file.name}-${index}`}>
                        {url ? (
                          <Link href={url} download>
                            {t("exports.download", { name: file.name })}
                          </Link>
                        ) : (
                          <span>
                            {t("exports.fileUnavailable", { name: file.name })}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </Disclosure>
  );
}
