import { t } from "../app/i18n";
import {
  Button as AriaButton,
  Link as AriaLink,
  Checkbox as AriaCheckbox,
  Disclosure as AriaDisclosure,
  DisclosurePanel,
  TooltipTrigger,
  Tooltip,
  composeRenderProps,
  type ButtonProps,
  type LinkProps,
  ToggleButton as AriaToggleButton,
  type ToggleButtonProps,
  Label,
  TextField,
  Input,
  TextArea,
  Modal,
  ModalOverlay,
  Dialog,
  Heading,
  Select,
  SelectValue,
  Popover,
  ListBox,
  ListBoxItem,
  Text,
  FieldError,
} from "react-aria-components";
import { useId, useState, type ReactNode, type RefAttributes } from "react";
export {
  Table,
  TableHeader,
  TableBody,
  Column,
  Row,
  Cell,
  GridList,
  GridListItem,
  Tabs,
  TabList,
  Tab,
  TabPanel,
  ToggleButtonGroup,
  I18nProvider,
} from "react-aria-components";
type Appearance = {
  variant?: "default" | "primary" | "quiet";
  size?: "regular" | "small";
};
export function Button({
  variant = "default",
  size = "regular",
  ...props
}: ButtonProps & Appearance & RefAttributes<HTMLButtonElement>) {
  return (
    <AriaButton
      {...props}
      className={composeRenderProps(
        props.className,
        (className) =>
          `control-button ${variant === "primary" ? "primary" : ""} variant-${variant} size-${size} ${className ?? ""}`,
      )}
    />
  );
}
export function ToggleButton(
  props: ToggleButtonProps & RefAttributes<HTMLButtonElement>,
) {
  return (
    <AriaToggleButton
      {...props}
      className={composeRenderProps(
        props.className,
        (className) => `control-button toggle-button ${className ?? ""}`,
      )}
    />
  );
}
export function Link(props: LinkProps & RefAttributes<HTMLAnchorElement>) {
  return (
    <AriaLink
      {...props}
      className={composeRenderProps(
        props.className,
        (className) => `control-link ${className ?? ""}`,
      )}
    />
  );
}
export function Check({
  children,
  selected,
  onChange,
  className = "",
  disabled = false,
}: {
  children: ReactNode;
  selected: boolean;
  onChange: (selected: boolean) => void;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <AriaCheckbox
      className={`check ${className}`}
      isSelected={selected}
      onChange={onChange}
      isDisabled={disabled}
    >
      <span className="checkbox-indicator" aria-hidden="true">
        <svg
          viewBox="0 0 16 16"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="m3 8 3 3 7-7" />
        </svg>
      </span>
      <span>{children}</span>
    </AriaCheckbox>
  );
}
export function Disclosure({
  title,
  children,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <AriaDisclosure className={`disclosure ${className}`}>
      <Button slot="trigger" className="disclosure-trigger">
        <svg
          aria-hidden="true"
          viewBox="0 0 12 12"
          width="12"
          height="12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="m4 2 4 4-4 4" />
        </svg>
        {title}
      </Button>
      <DisclosurePanel className="disclosure-panel">{children}</DisclosurePanel>
    </AriaDisclosure>
  );
}
export function Hint({
  children,
  text,
}: {
  children: ReactNode;
  text: string;
}) {
  return (
    <TooltipTrigger delay={400}>
      <Button className="tag hint-trigger">{children}</Button>
      <Tooltip className="tooltip" offset={8}>
        {text}
      </Tooltip>
    </TooltipTrigger>
  );
}
export function DialogSurface({
  title,
  children,
  onClose,
  dismissable = false,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  onClose: () => void;
  dismissable?: boolean;
  className?: string;
}) {
  return (
    <ModalOverlay
      isOpen
      isDismissable={dismissable}
      onOpenChange={(open) => !open && onClose()}
      className="overlay"
    >
      <Modal className={`modal ${className}`}>
        <Dialog>
          <Heading slot="title">{title}</Heading>
          {children}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
export function Field({
  label,
  value,
  onChange,
  multiline = false,
  description,
  required = false,
  inputId,
  error,
  contentLanguage,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  description?: string;
  required?: boolean;
  inputId?: string;
  error?: string;
  contentLanguage?: string;
}) {
  const labelId = useId();
  const [touched, setTouched] = useState(false);
  const invalid = Boolean(error || (required && touched && !value.trim()));
  return (
    <TextField
      aria-labelledby={labelId}
      className="field"
      value={value}
      onChange={onChange}
      isRequired={required}
      isInvalid={invalid}
      onBlur={() => setTouched(true)}
    >
      <Label id={labelId}>{label}</Label>
      {multiline ? (
        <TextArea id={inputId} lang={contentLanguage} />
      ) : (
        <Input id={inputId} lang={contentLanguage} />
      )}
      {description && (
        <Text slot="description" className="help">
          {description}
        </Text>
      )}
      {invalid && (
        <FieldError className="field-error">
          {error || t("field.required")}
        </FieldError>
      )}
    </TextField>
  );
}
export function Choice({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: {
    id: string;
    name: string;
  }[];
}) {
  const labelId = useId();
  return (
    <Select
      aria-labelledby={labelId}
      className="choice"
      selectedKey={value}
      onSelectionChange={(key) => onChange(String(key))}
    >
      <Label id={labelId}>{label}</Label>
      <Button>
        <SelectValue />
        <span aria-hidden="true" className="chevron">
          <svg
            viewBox="0 0 12 12"
            width="12"
            height="12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="m3 4.5 3 3 3-3" />
          </svg>
        </span>
      </Button>
      <Popover>
        <ListBox items={options}>
          {(item) => <ListBoxItem id={item.id}>{item.name}</ListBoxItem>}
        </ListBox>
      </Popover>
    </Select>
  );
}
export function Confirm({
  title,
  children,
  confirmLabel = t("common.continue"),
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <DialogSurface title={title} onClose={onCancel} dismissable>
      {children}
      <div className="actions">
        <Button onPress={onCancel}>{t("common.keepEditing")}</Button>
        <Button variant="primary" onPress={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </DialogSurface>
  );
}
export function Notice({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div
      className={`notice ${error ? "error" : ""}`}
      role={error ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
export function Icon({
  name,
}: {
  name: "cases" | "contacts" | "profile" | "settings" | "back";
}) {
  const paths = {
    cases: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    contacts:
      "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M17 4a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87",
    profile: "M20 21v-2a7 7 0 0 0-14 0v2 M13 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
    settings:
      "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2",
    back: "M19 12H5 M11 6l-6 6 6 6",
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
