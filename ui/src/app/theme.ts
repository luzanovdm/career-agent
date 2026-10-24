import { useEffect } from "react";
import type { Theme } from "../api/types";
/** Initial HTML data-theme is emitted by the runtime; CSS resolves system before paint. */
export function useTheme(theme: Theme) {
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    if (theme !== "system") {
      delete document.documentElement.dataset.osTheme;
      return;
    }
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.osTheme = media.matches
        ? "dark"
        : "light";
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
}
