import { useEffect, useState } from "react";
import type { Api } from "../api/client";
import type { Selection, VersionPage } from "../api/types";
import { Button, Choice, Notice } from "../ui/controls";
import { t, date, errorText } from "../app/i18n";
export function VersionBrowser({
  api,
  selection,
  workspaceId,
  revision,
  onSelect,
}: {
  api: Api;
  selection: Selection;
  workspaceId: string;
  revision: number;
  onSelect: (packetId: string, versionId: string | null) => void;
}) {
  const [open, setOpen] = useState(false),
    [page, setPage] = useState<VersionPage>(),
    [error, setError] = useState(""),
    [pending, setPending] = useState(false),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setPage(undefined);
    setError("");
    setPending(true);
    void api
      .versions(selection.packet_id, undefined, controller.signal)
      .then((result) => {
        if (result.workspace_id !== workspaceId || result.revision !== revision)
          throw new Error("Snapshot changed");
        if (!controller.signal.aborted) setPage(result);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorText(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setPending(false);
      });
    return () => controller.abort();
  }, [api, open, selection.packet_id, workspaceId, revision, retry]);
  async function more() {
    if (!page?.next_cursor || pending) return;
    setPending(true);
    try {
      const result = await api.versions(selection.packet_id, page.next_cursor);
      if (result.workspace_id !== workspaceId || result.revision !== revision)
        throw new Error("Snapshot changed");
      setPage({ ...result, items: [...page.items, ...result.items] });
    } catch (error) {
      setError(errorText(error as Error));
    } finally {
      setPending(false);
    }
  }
  const items = page?.items ?? [];
  const options = items.map((item) => ({
    id: item.id,
    name:
      t("version.item", {
        ordinal: item.ordinal,
        date: date(item.created_at),
      }) + (item.is_selected ? " · " + t("version.current") : ""),
  }));
  if (!options.some((option) => option.id === selection.version_id))
    options.unshift({ id: selection.version_id, name: t("version.viewed") });
  return (
    <div className="version-browser">
      <Button aria-expanded={open} onPress={() => setOpen((value) => !value)}>
        {t("version.browse")}
      </Button>
      {open && (
        <>
          <p>{t("version.readOnly")}</p>
          {pending && <p role="status">{t("common.loading")}</p>}
          {error && (
            <Notice error>
              {error}
              <Button onPress={() => setRetry((value) => value + 1)}>
                {t("common.retry")}
              </Button>
            </Notice>
          )}
          {page && (
            <>
              <Choice
                label={t("version.choose")}
                value={selection.version_id}
                options={options}
                onChange={(id) =>
                  onSelect(
                    selection.packet_id,
                    items.find((item) => item.id === id)?.is_selected
                      ? null
                      : id,
                  )
                }
              />
              <p>
                {t("version.count", {
                  count: page.items.length,
                  total: page.total,
                })}
              </p>
            </>
          )}
          {page?.next_cursor && (
            <Button onPress={() => void more()} isDisabled={pending}>
              {t("version.more")}
            </Button>
          )}
        </>
      )}
    </div>
  );
}
