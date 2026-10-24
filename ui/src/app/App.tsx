import { t, number, errorText } from "./i18n";
import { useTranslation } from "react-i18next";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  lazy,
  Suspense,
} from "react";
import { ToggleButtonGroup, ToggleButton, I18nProvider } from "../ui/controls";
import { api as defaultApi, Api, type ApiError } from "../api/client";
import { connectLive, type Connection } from "../api/live";
import type { Theme } from "../api/types";
import {
  Check,
  Link,
  Button,
  Choice,
  Confirm,
  Field,
  Icon,
  Notice,
} from "../ui/controls";
import { Cases } from "../features/Cases";
const Detail = lazy(() =>
  import("../features/Detail").then((module) => ({ default: module.Detail })),
);
const Profile = lazy(() =>
  import("../features/Profile").then((module) => ({ default: module.Profile })),
);
const Contacts = lazy(() =>
  import("../features/Contacts").then((module) => ({
    default: module.Contacts,
  })),
);
import { SaveButtons, SaveState, useDraft } from "../features/editing";
import { useSnapshot } from "./snapshot";
import { useTheme } from "./theme";
import type { AgentIntent } from "../api/types";
import { AgentPrompt } from "../features/AgentPrompt";
import { documentLanguage } from "./documentLanguage";
const statusLabels: Record<Connection, string> = {
  connecting: "connection.connecting",
  live: "connection.live",
  reconnecting: "connection.reconnecting",
  offline: "connection.offline",
  hidden: "connection.hidden",
  reauthenticate: "connection.reauthenticate",
};
const navigation = [
  { id: "cases", name: "nav.cases" },
  { id: "contacts", name: "nav.contacts" },
  { id: "profile", name: "nav.profile" },
  { id: "settings", name: "nav.settings" },
] as const;
export function App({
  api = defaultApi,
  capability = null,
  alreadyAuthenticated = false,
}: {
  api?: Api;
  capability?: string | null;
  alreadyAuthenticated?: boolean;
}) {
  const { i18n } = useTranslation();
  const [ready, setReady] = useState(alreadyAuthenticated),
    [sessionError, setSessionError] = useState<Error>(),
    [section, setSection] = useState("cases"),
    [view, setView] = useState<"board" | "table">("board"),
    [selected, setSelected] = useState<string | null>(null),
    [highlight, setHighlight] = useState<string | null>(null),
    [packet, setPacket] = useState<string | null>(null),
    [q, setQ] = useState(""),
    [search, setSearch] = useState(""),
    [agent, setAgent] = useState<AgentIntent>(),
    [track, setTrack] = useState(""),
    [closed, setClosed] = useState(false),
    [connection, setConnection] = useState<Connection>("connecting"),
    [dirty, setDirty] = useState<Record<string, boolean>>({}),
    [leave, setLeave] = useState<(() => void) | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setSearch(q), 300);
    return () => clearTimeout(timer);
  }, [q]);
  const sessionStarted = useRef(false);
  const hasDirty = Object.values(dirty).some(Boolean);
  const onDirty = useCallback(
    (id: string, value: boolean) =>
      setDirty((previous) =>
        previous[id] === value ? previous : { ...previous, [id]: value },
      ),
    [],
  );
  const navigate = useCallback(
    (action: () => void) => {
      if (hasDirty) setLeave(() => action);
      else action();
    },
    [hasDirty],
  );
  const snapshot = useSnapshot(
    api,
    ready,
    section,
    view,
    { q: search, track_id: track, closed },
    selected,
    packet,
  );
  const { data, error, refreshing, invalidate } = snapshot;
  const theme =
    data?.context.preferences.theme ??
    ((document.documentElement.dataset.theme as Theme) || "system");
  useTheme(theme);
  useEffect(() => {
    if (ready || sessionStarted.current) return;
    sessionStarted.current = true;
    const bootstrap = capability ? api.session(capability) : api.session("");
    void bootstrap
      .then(() => setReady(true))
      .catch((error) => setSessionError(error));
  }, [api, ready, capability]);
  useEffect(() => {
    if (!ready || !data) return;
    return connectLive(
      api,
      data.context.workspace_id,
      data.context.revision,
      invalidate,
      setConnection,
    );
  }, [api, ready, data?.context.workspace_id, invalidate]);
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (hasDirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasDirty]);
  const changeSection = (value: string) =>
    navigate(() => {
      setSection(value);
      setQ("");
    });
  const selectCase = (id: string) =>
    navigate(() => {
      setSelected(id);
      setHighlight(id);
      setPacket(null);
    });
  const selectedDetail =
    data?.detail?.case.id === selected ? data.detail : undefined;
  const casePage = data?.pages.table ?? data?.pages.qualify;
  const goBack = () =>
    navigate(() => {
      setSelected(null);
      setPacket(null);
      requestAnimationFrame(() =>
        document
          .querySelector<HTMLButtonElement>(
            `button[data-case-id="${CSS.escape(selected ?? "")}"]`,
          )
          ?.focus(),
      );
    });
  return (
    <I18nProvider locale={i18n.language || "en"}>
      <>
        <Link className="skip" href="#main">
          {t("app.skip")}
        </Link>
        <div className="shell">
          <aside className="sidebar" aria-label={t("nav.main")}>
            <div className="brand">{t("app.title")}</div>
            <p className="workspace-name">
              {data?.context.profile.display_name ?? t("app.private")}
            </p>
            <nav aria-label={t("nav.main")}>
              {navigation.map((item) => (
                <Button
                  key={item.id}
                  className={`nav-item ${section === item.id ? "active" : ""}`}
                  aria-current={section === item.id ? "page" : undefined}
                  onPress={() => changeSection(item.id)}
                >
                  <Icon name={item.id} />
                  <span>{t(item.name)}</span>
                  {item.id === "cases" && (
                    <span className="nav-count">
                      {data?.context.counts.cases ?? "—"}
                    </span>
                  )}
                </Button>
              ))}
            </nav>
            <div className="sidebar-tracks">
              <h2>{t("nav.tracks")}</h2>
              {data?.context.tracks.map((item) => (
                <Button
                  className={`track-link ${track === item.id ? "active" : ""}`}
                  key={item.id}
                  onPress={() =>
                    navigate(() => {
                      setSection("cases");
                      setSelected(null);
                      setTrack(item.id);
                    })
                  }
                >
                  {item.name}
                  <small>{item.language}</small>
                </Button>
              ))}
              {data?.context.tracks.length === 0 && <p>{t("nav.noTracks")}</p>}
            </div>
            <div className="sidebar-foot">
              <span className="avatar">CA</span>
              <div>
                <strong>{t("app.private")}</strong>
                <small>{t("app.local")}</small>
              </div>
            </div>
          </aside>
          <div className="workspace">
            <header className="topbar">
              <span>
                {t(
                  navigation.find((item) => item.id === section)?.name ??
                    "nav.cases",
                )}
                {selected && section === "cases"
                  ? ` / ${t("nav.caseDetail")}`
                  : ""}
              </span>
              <div className="topbar-status">
                <span
                  className={`connection ${connection === "live" ? "live" : ""}`}
                  role="status"
                >
                  {t(statusLabels[connection])}
                </span>
                <Button
                  size="small"
                  onPress={() => invalidate()}
                  isDisabled={!ready || refreshing}
                >
                  {refreshing ? t("common.refreshing") : t("common.refresh")}
                </Button>
              </div>
            </header>
            <nav className="mobile-nav" aria-label={t("nav.main")}>
              {navigation.map((item) => (
                <Button
                  key={item.id}
                  aria-current={section === item.id ? "page" : undefined}
                  onPress={() => changeSection(item.id)}
                >
                  {t(item.name)}
                </Button>
              ))}
            </nav>
            <main id="main" tabIndex={-1} aria-busy={refreshing}>
              {sessionError && (
                <Notice error>
                  {t("error.open")}{" "}
                  {(sessionError as ApiError).status === 401
                    ? t("error.session")
                    : errorText(sessionError)}
                </Notice>
              )}
              {error && (
                <Notice error>
                  {t("error.refresh")}
                  <Button onPress={() => invalidate()}>
                    {t("common.retry")}
                  </Button>
                </Notice>
              )}
              {!data && !error && !sessionError && (
                <div className="empty-state" role="status">
                  <h1>{t("loading.title")}</h1>
                  <p>{t("loading.description")}</p>
                </div>
              )}
              <Suspense fallback={<p role="status">{t("common.loading")}</p>}>
                {data && (
                  <>
                    {connection !== "live" && connection !== "connecting" && (
                      <div className="stale-banner" role="status">
                        {t(statusLabels[connection])}. {t("connection.stale")}
                      </div>
                    )}
                    {section === "cases" && (
                      <>
                        <section
                          hidden={Boolean(selected)}
                          aria-label={t("cases.title")}
                        >
                          <div className="page-heading">
                            <div>
                              <h1>{t("nav.cases")}</h1>
                              <p>
                                {t("cases.summary", {
                                  cases: t("cases.distinctCount", {
                                    count: casePage?.counts.total ?? 0,
                                  }),
                                  people: t("contacts.qualifiedCount", {
                                    count: casePage?.qualified_people ?? 0,
                                  }),
                                })}
                              </p>
                            </div>
                            <div className="overview-actions">
                              <Button
                                variant="primary"
                                onPress={() => setAgent("agent.research")}
                              >
                                {t("agent.research")}
                              </Button>
                              <ToggleButtonGroup
                                className="view-toggle"
                                aria-label={t("cases.layout")}
                                selectionMode="single"
                                disallowEmptySelection
                                selectedKeys={[view]}
                                onSelectionChange={(keys) =>
                                  setView([...keys][0] as "board" | "table")
                                }
                              >
                                <ToggleButton id="board">
                                  {t("cases.board")}
                                </ToggleButton>
                                <ToggleButton id="table">
                                  {t("cases.table")}
                                </ToggleButton>
                              </ToggleButtonGroup>
                            </div>
                          </div>
                          <div className="toolbar">
                            <Field
                              label={t("cases.search")}
                              value={q}
                              onChange={(value) => setQ(value)}
                            />
                            <Choice
                              label={t("cases.track")}
                              value={track || "all"}
                              onChange={(value) =>
                                setTrack(value === "all" ? "" : value)
                              }
                              options={[
                                { id: "all", name: t("cases.allTracks") },
                                ...data.context.tracks.map((item) => ({
                                  id: item.id,
                                  name: item.name,
                                })),
                              ]}
                            />
                            <Check selected={closed} onChange={setClosed}>
                              {t("cases.includeClosed")}
                            </Check>
                            <span className="help">{t("cases.countHint")}</span>
                          </div>
                          <Cases
                            pages={data.pages}
                            view={view}
                            selected={highlight}
                            onSelect={selectCase}
                            onMore={snapshot.more}
                            pending={refreshing}
                            onClear={() => {
                              setQ("");
                              setSearch("");
                              setTrack("");
                            }}
                          />
                        </section>
                        {selected && (
                          <>
                            <Button className="back-button" onPress={goBack}>
                              <Icon name="back" />
                              {t("nav.back")}
                            </Button>
                            {selectedDetail ? (
                              <Detail
                                key={selectedDetail.case.id}
                                detail={selectedDetail}
                                materialLanguage={documentLanguage(
                                  selectedDetail.case.tracks,
                                  data.context.tracks,
                                )}
                                api={api}
                                onDirty={onDirty}
                                refresh={invalidate}
                                onPacket={(id) => navigate(() => setPacket(id))}
                              />
                            ) : (
                              <p role="status">{t("common.loading")}</p>
                            )}
                          </>
                        )}
                      </>
                    )}
                    {section === "contacts" && (
                      <>
                        <div className="toolbar">
                          <Field
                            label={t("contacts.search")}
                            value={q}
                            onChange={(value) => navigate(() => setQ(value))}
                          />
                        </div>
                        <Contacts
                          page={data.contacts}
                          onMore={() => snapshot.more("contacts")}
                          pending={refreshing}
                          api={api}
                          onDirty={onDirty}
                          refresh={invalidate}
                          navigate={navigate}
                        />
                      </>
                    )}
                    {section === "profile" && (
                      <Profile
                        context={data.context}
                        api={api}
                        onDirty={onDirty}
                        refresh={invalidate}
                        onAgent={() => setAgent("agent.review")}
                      />
                    )}
                    {section === "settings" && (
                      <Settings
                        context={data.context}
                        api={api}
                        onDirty={onDirty}
                        refresh={invalidate}
                      />
                    )}
                  </>
                )}
              </Suspense>
            </main>
            <footer>
              <span>
                {t("app.private")} ·{" "}
                {data
                  ? t("app.revision", {
                      revision: number(data.context.revision),
                    })
                  : t("app.connecting")}
              </span>
              <span>
                {hasDirty ? t("app.unsavedTab") : t("app.savedSource")} ·{" "}
                {t("app.noSending")}
              </span>
            </footer>
          </div>
        </div>
        {agent && data && (
          <AgentPrompt
            api={api}
            intent={agent}
            workspaceId={data.context.workspace_id}
            revision={data.context.revision}
            tracks={data.context.tracks}
            trackId={section === "cases" ? track || undefined : undefined}
            onClose={() => setAgent(undefined)}
          />
        )}
        {leave && (
          <Confirm
            title={t("discard.title")}
            confirmLabel={t("discard.confirm")}
            onCancel={() => setLeave(null)}
            onConfirm={() => {
              const action = leave;
              setLeave(null);
              setDirty({});
              action();
            }}
          >
            <p>{t("discard.description")}</p>
          </Confirm>
        )}
      </>
    </I18nProvider>
  );
}
function Settings({
  context,
  api,
  onDirty,
  refresh,
}: {
  context: import("../api/types").Context;
  api: Api;
  onDirty: import("../features/editing").Dirty;
  refresh: (revision: number) => void;
}) {
  const draft = useDraft(
    "theme",
    context.preferences,
    context.revision,
    onDirty,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{t("nav.settings")}</h1>
          <p>{t("settings.description")}</p>
        </div>
      </div>
      <section className="panel settings">
        <h2>{t("settings.appearance")}</h2>
        <Choice
          label={t("settings.theme")}
          value={draft.value.theme}
          onChange={(theme) =>
            draft.setValue({ ...draft.value, theme: theme as Theme })
          }
          options={[
            { id: "system", name: t("settings.system") },
            { id: "light", name: t("settings.light") },
            { id: "dark", name: t("settings.dark") },
          ]}
        />
        <p>{t("settings.themeHint")}</p>
        <Choice
          label={t("settings.language")}
          value={draft.value.ui_locale ?? "en"}
          onChange={(ui_locale) =>
            draft.setValue({ ...draft.value, ui_locale })
          }
          options={[
            { id: "en", name: "English" },
            { id: "ru", name: "Русский" },
            ...(!["en", "ru"].includes(draft.value.ui_locale ?? "en")
              ? [{ id: draft.value.ui_locale!, name: draft.value.ui_locale! }]
              : []),
          ]}
        />
        <p>{t("settings.languageHint")}</p>
        <p>{t("settings.generatedLocale")}</p>
        <SaveState draft={draft} />
        <SaveButtons
          dirty={draft.dirty}
          pending={draft.pending}
          onCancel={draft.cancel}
          onSave={() =>
            void draft
              .save((value, revision) =>
                api.command("preferences.set", value, revision),
              )
              .then((r) => r && refresh(r.revision))
          }
        />
      </section>
      <section className="settings-info">
        <h2>{t("settings.research")}</h2>
        <p>
          {t(`research.${context.research.status}`)}.{" "}
          {t("settings.researchHint")}
        </p>
        <h2>{t("settings.runtime")}</h2>
        <p>{t("settings.runtimeHint")}</p>
      </section>
    </>
  );
}
