import type { CaseSummary } from "../api/types";
import { t } from "../app/i18n";
import { safeLink } from "../api/client";
import { Link } from "../ui/controls";

/** Display canonical route ownership; never infer a person from a mailbox. */
export function routeDisplay(item: CaseSummary) {
  const selected = item.selected_route;
  const unknown = {
    recipient: t("cases.routeMissing"),
    label: t("cases.routeUnknown"),
    value: undefined as string | undefined,
    href: undefined as string | undefined,
    qualified: false,
  };
  let route: { kind?: string; value?: string } | null | undefined;
  let recipient: string;
  let label: string;
  let qualified = false;
  if (item.route === "company") {
    recipient = t("cases.mailboxMissing");
    label = t("cases.routeCompany");
    route =
      selected?.owner === "company" && selected.kind === "email"
        ? selected
        : null;
    if (route?.value) recipient = route.value;
    qualified = !!selected?.qualified;
  } else if (item.route === "person") {
    recipient = item.contact?.name ?? t("cases.contactMissing");
    label = t("cases.routePerson");
    route =
      selected === undefined
        ? item.contact?.route
        : selected?.owner === "person"
          ? selected
          : null;
    qualified = selected?.qualified ?? !!item.contact?.qualified;
  } else if (item.route === "form") {
    recipient = t("cases.formRecipient");
    label = t("cases.routeForm");
    route =
      selected?.owner === "case" && selected.kind === "form" ? selected : null;
    qualified = !!selected?.qualified;
  } else return unknown;
  const value = route?.value;
  let href: string | undefined;
  if (value && route?.kind === "email") {
    // No mailto headers, extra recipients, query or fragment injection.
    if (/^[^\s@<>?&#]+@[^\s@<>?&#]+\.[^\s@<>?&#]+$/.test(value))
      href = `mailto:${encodeURIComponent(value).replace(/%40/g, "@")}`;
  } else if (
    value &&
    /^(profile|form|website)$/.test(route?.kind ?? "") &&
    /^https?:\/\//i.test(value)
  ) {
    href = safeLink(value);
  }
  return { recipient, label, value, href, qualified: qualified && !!href };
}

export function RouteIdentity({
  item,
  emphasize = false,
}: {
  item: CaseSummary;
  emphasize?: boolean;
}) {
  const route = routeDisplay(item);
  return (
    <>
      {emphasize ? (
        <strong>{route.recipient}</strong>
      ) : (
        <span>{route.recipient}</span>
      )}
      <span className="muted"> · {route.label}</span>
    </>
  );
}

export function RouteLink({ item }: { item: CaseSummary }) {
  const route = routeDisplay(item);
  if (!route.value) return null;
  return (
    <p className="professional-route">
      {route.href ? (
        <Link
          href={route.href}
          target={route.href.startsWith("mailto:") ? undefined : "_blank"}
          rel="noopener noreferrer"
          referrerPolicy="no-referrer"
        >
          {route.value}
        </Link>
      ) : (
        <span>{route.value}</span>
      )}
      {" · "}
      {t(route.qualified ? "cases.routeVerified" : "cases.routePending")}
    </p>
  );
}
