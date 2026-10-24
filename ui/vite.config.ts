import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
const bootstrapKeys = ["error.open", "error.operation", "common.retry"];
export default defineConfig({
  plugins: [
    react(),
    {
      name: "career-bootstrap-translations",
      resolveId(id) {
        return id === "virtual:career-bootstrap"
          ? "\0career-bootstrap"
          : undefined;
      },
      load(id) {
        if (id !== "\0career-bootstrap") return;
        const catalogs = Object.fromEntries(
          ["en", "ru"].map((locale) => {
            const source = JSON.parse(
              readFileSync(
                new URL(`./public/locales/${locale}.json`, import.meta.url),
                "utf8",
              ),
            );
            return [
              locale,
              {
                ...source,
                messages: Object.fromEntries(
                  bootstrapKeys.map((key) => [key, source.messages[key]]),
                ),
              },
            ];
          }),
        );
        return "export default " + JSON.stringify(catalogs);
      },
    },
  ],
  build: { target: "es2022", sourcemap: false },
  server: { host: "127.0.0.1" },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
