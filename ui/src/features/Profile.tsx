import { useEffect, useRef, useState } from "react";
import type { Api } from "../api/client";
import type { Context, Track } from "../api/types";
import { t } from "../app/i18n";
import { Check, Disclosure, Button, Field, Choice } from "../ui/controls";
import {
  SaveButtons,
  SaveState,
  useDraft,
  useEditorMode,
  type Dirty,
} from "./editing";
function languageName(value: string) {
  try {
    return (
      new Intl.DisplayNames([document.documentElement.lang || "en"], {
        type: "language",
      }).of(value) ?? value
    );
  } catch {
    return value;
  }
}
function languageOptions(current: string) {
  return [...new Set([current, "en", "ru"])]
    .filter(Boolean)
    .map((id) => ({ id, name: languageName(id) }));
}
function Policies({ track }: { track: Track }) {
  return (
    <Disclosure title={t("profile.policies")}>
      <dl className="policy-summary">
        {Object.entries(track.policies).map(([key, raw]) => {
          const policy = raw as { state?: string; value?: unknown };
          return (
            <div key={key}>
              <dt>
                {t(
                  key === "geography"
                    ? "profile.policyGeography"
                    : key === "compensation"
                      ? "profile.policyCompensation"
                      : key === "language"
                        ? "profile.policyLanguage"
                        : "profile.policies",
                )}
              </dt>
              <dd>
                {policy.state === "unknown"
                  ? t("profile.policyUnknown")
                  : typeof policy.value === "string" ||
                      typeof policy.value === "number"
                    ? String(policy.value)
                    : t("common.none")}
              </dd>
            </div>
          );
        })}
      </dl>
    </Disclosure>
  );
}
export function Profile({
  context,
  api,
  onDirty,
  refresh,
  onAgent,
}: {
  context: Context;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
  onAgent: () => void;
}) {
  const draft = useDraft("profile", context.profile, context.revision, onDirty),
    [adding, setAdding] = useState(false);
  const { editing, setEditing, editTrigger, cancelEditing } = useEditorMode();
  const addTrigger = useRef<HTMLButtonElement>(null);
  const returnToAdd = useRef(false);
  useEffect(() => {
    if (!adding && returnToAdd.current) {
      addTrigger.current?.focus();
      returnToAdd.current = false;
    }
  }, [adding]);
  useEffect(() => {
    if (draft.receipt && !draft.dirty && !draft.pending) setEditing(false);
  }, [draft.receipt, draft.dirty, draft.pending]);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{t("profile.title")}</h1>
          <p>{t("profile.description")}</p>
        </div>
        <Button variant="primary" onPress={onAgent}>
          {t("profile.withAgent")}
        </Button>
      </div>
      <div className="profile-layout">
        <section className="panel">
          <div className="section-heading">
            <h2>{t("profile.profile")}</h2>
            {!editing && (
              <Button ref={editTrigger} onPress={() => setEditing(true)}>
                {t("common.edit")}
              </Button>
            )}
          </div>
          {editing ? (
            <>
              <Field
                label={t("profile.name")}
                value={draft.value.display_name}
                onChange={(display_name) =>
                  draft.setValue({ ...draft.value, display_name })
                }
              />
              <Choice
                label={t("profile.conversationLanguage")}
                value={draft.value.conversation_language}
                onChange={(conversation_language) =>
                  draft.setValue({ ...draft.value, conversation_language })
                }
                options={languageOptions(draft.value.conversation_language)}
              />
              <p className="help">{t("profile.languageHint")}</p>
              <SaveState
                draft={draft}
                latest={
                  <dl>
                    <dt>{t("profile.name")}</dt>
                    <dd>{context.profile.display_name}</dd>
                    <dt>{t("profile.conversationLanguage")}</dt>
                    <dd>
                      {languageName(context.profile.conversation_language)}
                    </dd>
                  </dl>
                }
              />
              <SaveButtons
                dirty={draft.dirty}
                pending={draft.pending}
                onCancel={() => {
                  draft.cancel();
                  cancelEditing();
                }}
                onSave={() =>
                  void draft
                    .save((input, revision) =>
                      api.command("profile.update", input, revision),
                    )
                    .then((result) => result && refresh(result.revision))
                }
              />
            </>
          ) : (
            <dl>
              <dt>{t("profile.name")}</dt>
              <dd>{context.profile.display_name}</dd>
              <dt>{t("profile.conversationLanguage")}</dt>
              <dd>{languageName(context.profile.conversation_language)}</dd>
            </dl>
          )}
        </section>
        <section className="tracks">
          <div className="section-heading">
            <h2>{t("profile.tracks")}</h2>
            <Button
              ref={addTrigger}
              isDisabled={adding}
              onPress={() => setAdding(true)}
            >
              {t("profile.addTrack")}
            </Button>
          </div>
          {context.tracks.map((track) => (
            <TrackEditor
              key={track.id}
              track={track}
              context={context}
              api={api}
              onDirty={onDirty}
              refresh={refresh}
            />
          ))}
          {adding && (
            <TrackEditor
              track={{
                id: "",
                name: "",
                positioning: "",
                selected: false,
                language: context.profile.conversation_language,
                policies: {},
              }}
              context={context}
              api={api}
              onDirty={onDirty}
              refresh={(revision) => {
                setAdding(false);
                refresh(revision);
              }}
              onCancel={() => {
                returnToAdd.current = true;
                setAdding(false);
              }}
            />
          )}
        </section>
      </div>
    </>
  );
}
function TrackEditor({
  track,
  context,
  api,
  onDirty,
  refresh,
  onCancel,
}: {
  track: Track;
  context: Context;
  api: Api;
  onDirty: Dirty;
  refresh: (revision: number) => void;
  onCancel?: () => void;
}) {
  const draft = useDraft(
    `track-${track.id || "new"}`,
    track,
    context.revision,
    onDirty,
  );
  const { editing, setEditing, editTrigger, cancelEditing } = useEditorMode(
    !track.id,
  );
  useEffect(() => {
    if (draft.receipt && !draft.dirty && !draft.pending) setEditing(false);
  }, [draft.receipt, draft.dirty, draft.pending]);
  return (
    <section className="panel">
      <div className="section-heading">
        <h3>{track.name || t("profile.newTrack")}</h3>
        {!editing && (
          <Button ref={editTrigger} onPress={() => setEditing(true)}>
            {t("common.edit")}
          </Button>
        )}
      </div>
      {editing ? (
        <>
          <Field
            label={t("profile.trackName")}
            value={draft.value.name}
            onChange={(name) => draft.setValue({ ...draft.value, name })}
            required
          />
          <Field
            label={t("profile.positioning")}
            multiline
            value={draft.value.positioning}
            onChange={(positioning) =>
              draft.setValue({ ...draft.value, positioning })
            }
          />
          <Choice
            label={t("profile.documentLanguage")}
            value={draft.value.language}
            onChange={(language) =>
              draft.setValue({ ...draft.value, language })
            }
            options={languageOptions(draft.value.language)}
          />
          <Check
            selected={draft.value.selected}
            onChange={(selected) =>
              draft.setValue({ ...draft.value, selected })
            }
          >
            {t("profile.selected")}
          </Check>
          <SaveState
            draft={draft}
            latest={
              <>
                <p>{track.name}</p>
                <p>{track.positioning}</p>
                <p>{languageName(track.language)}</p>
              </>
            }
          />
          <SaveButtons
            dirty={draft.dirty}
            valid={Boolean(draft.value.name.trim())}
            pending={draft.pending}
            onCancel={() => {
              draft.cancel();
              cancelEditing();
              onCancel?.();
            }}
            onSave={() =>
              void draft
                .save((value, revision) =>
                  api.command(
                    "track.save",
                    { ...value, ...(!track.id ? { id: undefined } : {}) },
                    revision,
                  ),
                )
                .then((result) => result && refresh(result.revision))
            }
          />
        </>
      ) : (
        <>
          <p>{track.positioning}</p>
          <p className="help">
            {t("profile.documentLanguage")}: {languageName(track.language)}
          </p>
        </>
      )}
      <Policies track={track} />
    </section>
  );
}
