import { t, loadInitialLocale, initializeLocale } from "./app/i18n";
import { Button } from "./ui/controls";
import bootstrapCatalogs from "virtual:career-bootstrap";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { takeLaunchCapability } from "./api/client";
import { App } from "./app/App";
import "./styles/system.css";
// Strip the one-use capability before any request or rendering work.
const capability = takeLaunchCapability();
class Boundary extends Component<
  {
    children: ReactNode;
  },
  {
    failed: boolean;
  }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* No telemetry or private data logging. */
  }
  render() {
    return this.state.failed ? (
      <main>
        <h1>{t("error.viewTitle")}</h1>
        <p>{t("error.viewDescription")}</p>
      </main>
    ) : (
      this.props.children
    );
  }
}
const root = createRoot(document.getElementById("root")!);
async function start() {
  try {
    await loadInitialLocale();
    root.render(
      <Boundary>
        <App capability={capability} />
      </Boundary>,
    );
  } catch {
    await initializeLocale(
      bootstrapCatalogs[
        document.documentElement.lang.startsWith("ru") ? "ru" : "en"
      ],
    );
    root.render(
      <main>
        <h1>{t("error.open")}</h1>
        <p role="alert">{t("error.operation")}</p>
        <Button onPress={() => void start()}>{t("common.retry")}</Button>
      </main>,
    );
  }
}
await start();
