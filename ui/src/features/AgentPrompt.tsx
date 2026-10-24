import { useEffect, useRef, useState } from "react";
import type { Api } from "../api/client";
import type { AgentHandoff, AgentIntent } from "../api/types";
import { t, errorText } from "../app/i18n";
import {
  DialogSurface,
  Disclosure,
  Button,
  Choice,
  Field,
  Notice,
} from "../ui/controls";
export function AgentPrompt({
  api,
  intent: initialIntent,
  caseId,
  workspaceId,
  revision,
  instruction = "",
  scopeLabel,
  tracks = [],
  trackId,
  onClose,
}: {
  api: Api;
  intent: AgentIntent;
  caseId?: string;
  workspaceId: string;
  revision: number;
  instruction?: string;
  scopeLabel?: string;
  tracks?: readonly { id: string; name: string }[];
  trackId?: string;
  onClose: () => void;
}) {
  const [intent, setIntent] = useState(initialIntent),
    [handoff, setHandoff] = useState<AgentHandoff>(),
    [prompt, setPrompt] = useState(""),
    [error, setError] = useState(""),
    [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle"),
    [refresh, setRefresh] = useState(0),
    [previousDraft, setPreviousDraft] = useState("");
  const generation = useRef(0),
    drafts = useRef<Record<string, { id: string; prompt: string }>>({});
  useEffect(() => {
    const controller = new AbortController(),
      request = ++generation.current;
    setError("");
    setCopy("idle");
    setHandoff(undefined);
    void api
      .agentIntent(intent, caseId, controller.signal, trackId)
      .then((result) => {
        if (request !== generation.current || controller.signal.aborted) return;
        if (
          result.workspace_id !== workspaceId ||
          result.executed !== false ||
          result.external_actions.performed !== 0 ||
          result.descriptor.status !== "not_executed" ||
          result.descriptor.workspace_id !== workspaceId ||
          result.descriptor.intent !== intent ||
          (trackId &&
            (result.descriptor.scope.track_ids.length !== 1 ||
              result.descriptor.scope.track_ids[0] !== trackId)) ||
          (caseId && !result.descriptor.scope.case_ids.includes(caseId))
        )
          throw new Error("Invalid handoff");
        setHandoff(result);
        const retained = drafts.current[intent];
        if (retained && retained.id !== result.descriptor.id)
          setPreviousDraft(retained.prompt);
        setPrompt(
          retained?.id === result.descriptor.id
            ? retained.prompt
            : `${result.prompt}${instruction ? "\n\n" + instruction : ""}`,
        );
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorText(error));
      });
    return () => controller.abort();
  }, [api, intent, caseId, workspaceId, refresh, instruction, trackId]);
  const stale = handoff && handoff.revision !== revision;
  const selectText = () => {
    const input = document.getElementById(
      "agent-prompt-text",
    ) as HTMLTextAreaElement | null;
    input?.focus();
    input?.select();
  };
  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopy("copied");
    } catch {
      setCopy("failed");
      selectText();
    }
  }
  return (
    <DialogSurface
      title={t("agent.title")}
      onClose={onClose}
      dismissable
      className="agent-modal"
    >
      <p>{t("agent.description")}</p>
      <Choice
        label={t("agent.intent")}
        value={intent}
        onChange={(value) => {
          if (handoff)
            drafts.current[intent] = { id: handoff.descriptor.id, prompt };
          setIntent(value as AgentIntent);
        }}
        options={(
          ["agent.research", "agent.prepare", "agent.review"] as const
        ).map((id) => ({ id, name: t(id) }))}
      />
      {handoff && (
        <section className="handoff-scope" aria-label={t("agent.scope")}>
          <strong>{t("agent.scope")}</strong>
          <p>{scopeLabel ?? t("agent.workspaceScope")}</p>
          <p>
            {t("agent.namedTracks", {
              tracks:
                handoff.descriptor.scope.track_ids
                  .map(
                    (id) =>
                      tracks.find((track) => track.id === id)?.name ??
                      t("agent.unnamedTrack"),
                  )
                  .join(", ") || t("common.none"),
            })}
          </p>
          <Disclosure title={t("common.details")}>
            <dl>
              <dt>{t("app.private")}</dt>
              <dd>{handoff.workspace_id}</dd>
              <dt>{t("detail.version")}</dt>
              <dd>{handoff.descriptor.scope.version_ids.join(", ") || "—"}</dd>
              <dt>{t("nav.tracks")}</dt>
              <dd>{handoff.descriptor.scope.track_ids.join(", ") || "—"}</dd>
            </dl>
          </Disclosure>
        </section>
      )}
      {!handoff && !error && <p role="status">{t("agent.loading")}</p>}
      {error && (
        <Notice error>
          {t("agent.failed")}
          <Button
            onPress={() => {
              if (handoff)
                drafts.current[intent] = {
                  id: handoff.descriptor.id,
                  prompt,
                };
              setRefresh((n) => n + 1);
            }}
          >
            {t("common.retry")}
          </Button>
        </Notice>
      )}
      {stale && (
        <Notice error>
          {t("agent.stale")}
          <Button
            onPress={() => {
              if (handoff)
                drafts.current[intent] = {
                  id: handoff.descriptor.id,
                  prompt,
                };
              setRefresh((n) => n + 1);
            }}
          >
            {t("common.refresh")}
          </Button>
        </Notice>
      )}
      {handoff && (
        <Field
          inputId="agent-prompt-text"
          label={t("agent.prompt")}
          multiline
          value={prompt}
          onChange={(value) => {
            setPrompt(value);
            setCopy("idle");
          }}
        />
      )}
      {previousDraft && (
        <Disclosure title={t("agent.previousDraft")}>
          <pre>{previousDraft}</pre>
        </Disclosure>
      )}
      <p className="help">{t("agent.noExecution")}</p>
      {copy !== "idle" && (
        <Notice error={copy === "failed"}>
          {t(copy === "copied" ? "agent.copied" : "agent.copyFailed")}
          {copy === "failed" && (
            <Button onPress={selectText}>{t("agent.select")}</Button>
          )}
        </Notice>
      )}
      <div className="actions">
        <Button onPress={onClose}>{t("common.close")}</Button>
        <Button
          variant="primary"
          isDisabled={!handoff || !prompt || Boolean(stale)}
          onPress={() => void copyPrompt()}
        >
          {t("agent.copy")}
        </Button>
      </div>
    </DialogSurface>
  );
}
