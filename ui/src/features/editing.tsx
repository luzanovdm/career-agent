import { t, issueText, errorText, number } from "../app/i18n";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, UncertainCommand } from "../api/client";
import type { Receipt } from "../api/types";
import { Disclosure, Button, Notice } from "../ui/controls";
export type Dirty = (id: string, dirty: boolean) => void;
/** Restore the reading trigger after a disappearing editor is canceled. */
export function useEditorMode(initial = false) {
  const [editing, setEditing] = useState(initial);
  const editTrigger = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  useEffect(() => {
    if (!editing && returnFocus.current) {
      editTrigger.current?.focus();
      returnFocus.current = false;
    }
  }, [editing]);
  return {
    editing,
    setEditing,
    editTrigger,
    cancelEditing: () => {
      returnFocus.current = true;
      setEditing(false);
    },
  };
}
export function useDraft<T>(
  id: string,
  initial: T,
  revision: number,
  onDirty: Dirty,
) {
  const [base, setBase] = useState({ value: initial, revision });
  const [value, setValue] = useState(initial);
  const [failure, setFailure] = useState<Error>();
  const [receipt, setReceipt] = useState<Receipt>();
  const [pending, setPending] = useState(false);
  const dirty = JSON.stringify(base.value) !== JSON.stringify(value),
    conflict = dirty && revision > base.revision;
  const initialKey = JSON.stringify(initial);
  useEffect(() => {
    if (
      revision >= base.revision &&
      (!dirty ||
        (receipt?.revision === revision &&
          initialKey === JSON.stringify(value)))
    ) {
      setBase({ value: initial, revision });
      setValue(initial);
    }
  }, [revision, initialKey]);
  useEffect(() => {
    onDirty(id, dirty);
    return () => onDirty(id, false);
  }, [id, dirty, onDirty]);
  const save = async (
    action: (value: T, revision: number) => Promise<Receipt>,
  ) => {
    setPending(true);
    setFailure(undefined);
    setReceipt(undefined);
    try {
      const result = await action(value, base.revision);
      setReceipt(result);
      if (result.outcome === "satisfied") {
        setBase({ value, revision: result.revision });
      }
      return result;
    } catch (error) {
      setFailure(error as Error);
      return undefined;
    } finally {
      setPending(false);
    }
  };
  const cancel = () => {
    setValue(initial);
    setBase({ value: initial, revision });
    setFailure(undefined);
    setReceipt(undefined);
  };
  return {
    value,
    setValue,
    base,
    dirty,
    conflict,
    pending,
    failure,
    receipt,
    save,
    cancel,
    merge: () => {
      setBase({ value: initial, revision });
      setFailure(undefined);
    },
    clearReceipt: () => setReceipt(undefined),
  };
}
export function SaveState({
  draft,
  latest,
}: {
  draft: {
    dirty: boolean;
    conflict: boolean;
    pending: boolean;
    failure?: Error;
    receipt?: Receipt;
    cancel: () => void;
    merge: () => void;
  };
  latest?: ReactNode;
}) {
  return (
    <>
      {draft.conflict && (
        <Notice error>
          {t("save.conflict")}
          {latest && (
            <Disclosure title={t("save.compare")}>{latest}</Disclosure>
          )}
          <div className="actions">
            <Button onPress={draft.cancel}>{t("save.useCurrent")}</Button>
            <Button onPress={draft.merge}>{t("save.keepDraft")}</Button>
          </div>
        </Notice>
      )}
      {draft.failure && (
        <Notice error>
          {draft.failure instanceof ApiError && draft.failure.status === 409
            ? t("save.conflictFailure")
            : errorText(draft.failure)}
          {draft.failure instanceof UncertainCommand && (
            <p>{t("save.request", { id: draft.failure.request_id })}</p>
          )}
        </Notice>
      )}
      {draft.receipt && (
        <Notice error={draft.receipt.outcome === "partial"}>
          {draft.receipt.outcome === "partial"
            ? t("save.partial")
            : t("save.success", { revision: number(draft.receipt.revision) })}
          {draft.receipt.issues.map((issue, index) => (
            <p key={`${issue.code}-${index}`}>{issueText(issue)}</p>
          ))}
        </Notice>
      )}
    </>
  );
}
export function SaveButtons({
  dirty,
  pending,
  onSave,
  onCancel,
  valid = true,
}: {
  dirty: boolean;
  pending: boolean;
  onSave: () => void;
  onCancel: () => void;
  valid?: boolean;
}) {
  return (
    <div className="actions save-actions">
      <Button
        variant="primary"
        isDisabled={!dirty || pending || !valid}
        onPress={onSave}
      >
        {pending ? t("common.saving") : t("common.save")}
      </Button>
      <Button isDisabled={pending} onPress={onCancel}>
        {t("common.cancel")}
      </Button>
      <span role="status">
        {pending ? t("common.pending") : dirty ? t("common.unsaved") : ""}
      </span>
    </div>
  );
}
