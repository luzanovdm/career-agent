import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import {
  context,
  detail,
  page as casePage,
  contacts,
  receipt,
  board,
  handoff,
} from "../tests/fixtures";
const catalogs = Object.fromEntries(
  ["en", "ru"].map((locale) => [
    locale,
    JSON.parse(readFileSync(`public/locales/${locale}.json`, "utf8")),
  ]),
);
async function mock(
  page: Page,
  theme: "light" | "dark" | "system" = "system",
  locale = "en",
) {
  await page.addInitScript(() => {
    class TestStream extends EventTarget {
      readyState = 1;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      constructor(_url: string) {
        super();
        setTimeout(() => this.onopen?.(new Event("open")), 0);
      }
      close() {
        this.readyState = 2;
      }
    }
    Object.defineProperty(window, "EventSource", { value: TestStream });
  });
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/session")
      return route.fulfill({
        json: {
          csrf_token: "fictional-csrf",
          protocol: "career-agent.local/1",
        },
      });
    if (url.pathname === "/api/v1/context")
      return route.fulfill({
        json: {
          ...context,
          ...(url.searchParams.has("task")
            ? {
                evidence: { claims: [], answers: [], sources: [] },
                pagination: Object.fromEntries(
                  ["claims", "answers", "sources", "tracks"].map((key) => [
                    key,
                    {
                      total: 0,
                      returned: 0,
                      remaining: 0,
                      offset: 0,
                      available: 0,
                      omitted_by_scope: 0,
                    },
                  ]),
                ),
                partial: false,
                next_cursor: null,
              }
            : {}),
          preferences: { theme, ui_locale: locale },
        },
      });
    if (url.pathname === "/api/v1/board")
      return route.fulfill({ json: board() });
    if (url.pathname === "/api/v1/cases")
      return route.fulfill({
        json: casePage(url.searchParams.get("column") ?? undefined),
      });
    if (url.pathname === `/api/v1/cases/${detail.case.id}`)
      return route.fulfill({ json: detail });
    if (url.pathname === "/api/v1/history/observations")
      return route.fulfill({
        json: {
          ...context,
          items: [],
          total: 0,
          next_cursor: null,
          pending_projection: 0,
          projection_current: true,
        },
      });
    if (url.pathname === "/api/v1/contacts")
      return route.fulfill({ json: contacts });
    if (url.pathname === "/api/v1/changes")
      return route.fulfill({
        json: { ...context, changes: [], resync_required: false },
      });
    if (url.pathname === "/api/v1/commands")
      return route.fulfill({ json: receipt });
    if (url.pathname === "/api/v1/localization") {
      const catalog = catalogs[url.searchParams.get("locale") ?? locale];
      return route.fulfill({
        json: {
          ...context,
          locale: catalog.locale,
          catalog: catalog.messages,
          plural_categories: catalog.plural_categories,
          fallback_locale: "en",
        },
      });
    }
    if (url.pathname === "/api/v1/agent-intent") {
      const intent = url.searchParams.get("intent") ?? "agent.review",
        messages = catalogs[locale].messages,
        descriptor = {
          ...handoff.descriptor,
          intent,
          ...(url.searchParams.has("packet_id")
            ? { selection_mode: "packet" }
            : {}),
          scope: {
            ...handoff.descriptor.scope,
            ...(url.searchParams.has("packet_id")
              ? { packet_ids: [url.searchParams.get("packet_id")!] }
              : {}),
            ...(url.searchParams.has("track_id")
              ? { track_ids: [url.searchParams.get("track_id")!] }
              : {}),
          },
        };
      const prompt = messages["agentPrompt.boundPrompt"]
        .replace("{workspace_id}", context.workspace_id)
        .replace("{descriptor}", JSON.stringify(descriptor))
        .replace(
          "{action}",
          messages["agentPrompt." + intent.split(".")[1] + "Instruction"],
        );
      return route.fulfill({ json: { ...handoff, descriptor, prompt } });
    }
    return route.fulfill({
      status: 404,
      json: {
        error: { code: "NOT_FOUND", message: "Unknown fictional route" },
      },
    });
  });
}
test("shared kit keyboard: grouped stages, collection, checkbox, disclosure, tooltip and dialog", async ({
  page,
}) => {
  await mock(page, "light", "en");
  const detailReads: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/v1/cases/"))
      detailReads.push(request.url());
  });
  await page.goto("/");
  const stages = page.locator(".stage-strip");
  const first = stages.getByRole("radio").first();
  await first.focus();
  await page.keyboard.press("ArrowRight");
  await expect(stages.getByRole("radio").nth(1)).toBeFocused();
  await page.keyboard.press("Space");
  await expect(stages.getByRole("radio").nth(1)).toBeChecked();
  await expect(stages.getByRole("radio", { checked: true })).toHaveCount(1);
  const hide = page.getByRole("checkbox", { name: "Hide empty stages" });
  await hide.focus();
  await page.keyboard.press("Space");
  await expect(hide).not.toBeChecked();
  const grid = page.getByRole("grid", { name: "Prepare / revise: cards" });
  await grid.focus();
  await page.keyboard.press("ArrowDown");
  await expect(grid.getByRole("row").first()).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".detail-heading h1")).toBeFocused();
  const hint = page.locator(".detail-heading .hint-trigger").first();
  await hint.focus();
  await expect(page.getByRole("tooltip")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).not.toBeVisible();
  expect(detailReads).toHaveLength(1);
  const version = page.getByRole("button", {
    name: "Saved version",
    exact: true,
  });
  await version.focus();
  await page.keyboard.press("Space");
  await expect(version).toHaveAttribute("aria-expanded", "true");
  const agent = page.locator(".agent-entry");
  await agent.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(agent).toBeFocused();
});

test("required track name uses shared inline error and cannot save blank input", async ({
  page,
}) => {
  await mock(page, "light", "en");
  await page.goto("/");
  await page
    .getByRole("button", { name: "Profile & tracks", exact: true })
    .click();
  await page.getByRole("button", { name: "Add track", exact: true }).click();
  const name = page.getByRole("textbox", { name: "Track name" });
  await name.fill("Temporary track");
  await name.fill("   ");
  await name.press("Tab");
  await expect(name).toHaveAttribute("aria-invalid", "true");
  const error = page.getByText("This field is required.", { exact: true });
  await expect(error).toBeVisible();
  await expect(name).toHaveAttribute(
    "aria-describedby",
    new RegExp((await error.getAttribute("id"))!),
  );
  await expect(
    page.getByRole("button", { name: "Save changes", exact: true }),
  ).toBeDisabled();
});

test("pristine edit Cancel returns to reading and exits new track editor", async ({
  page,
}) => {
  await mock(page, "light", "en");
  await page.goto("/");
  await page
    .getByRole("button", { name: "Open Aurora Example: Product engineer" })
    .click();
  await expect(page.locator(".detail-heading h1")).toBeFocused();
  await page.getByRole("button", { name: "Edit draft", exact: true }).click();
  const materials = page.locator("#material-editor");
  await expect(
    materials.getByRole("button", { name: "Cancel", exact: true }),
  ).toBeEnabled();
  await materials.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Edit draft", exact: true }),
  ).toBeFocused();
  await expect(
    materials.getByRole("article", { name: "Saved document" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Profile & tracks", exact: true })
    .click();
  await page.getByRole("button", { name: "Add track", exact: true }).click();
  const editor = page
    .locator("section.panel")
    .filter({ has: page.getByRole("textbox", { name: "Track name" }) });
  await editor.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Add track", exact: true }),
  ).toBeFocused();
  await expect(page.getByRole("textbox", { name: "Track name" })).toHaveCount(
    0,
  );
});

test("filtered research handoff binds and names only the selected career direction", async ({
  page,
}) => {
  await mock(page, "light", "en");
  await page.goto("/");
  await page.locator(".sidebar-tracks button").first().click();
  const response = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/v1/agent-intent",
  );
  await page
    .getByRole("button", { name: "Find opportunities", exact: true })
    .click();
  const request = await response;
  expect(new URL(request.url()).searchParams.get("track_id")).toBe(
    context.tracks[0].id,
  );
  const scope = page.locator(".handoff-scope");
  await expect(scope).toContainText(
    "Career directions: " + context.tracks[0].name,
  );
  await expect(scope).not.toContainText(context.tracks[1].name);
});

for (const locale of ["en", "ru"])
  for (const mode of ["light", "dark", "system"] as const)
    for (const size of ["desktop", "mobile"] as const) {
      test(`board ${locale} ${mode} ${size}: axe and screenshot`, async ({
        page,
      }) => {
        await page.setViewportSize(
          size === "desktop"
            ? { width: 1440, height: 1000 }
            : { width: 390, height: 844 },
        );
        await page.emulateMedia({
          colorScheme: mode === "light" ? "light" : "dark",
          reducedMotion: "reduce",
        });
        await mock(page, mode, locale);
        await page.goto("/");
        await expect(page.locator("html")).toHaveAttribute("lang", locale);
        await expect(page.locator(".stage-strip button")).toHaveCount(6);
        if (size === "mobile")
          await page.locator(".stage-strip button").nth(1).click();
        await expect(
          page.getByRole("button", {
            name:
              locale === "en"
                ? "Open Aurora Example: Product engineer"
                : "Открыть Aurora Example: Product engineer",
          }),
        ).toBeVisible();
        await expect(page.locator("html")).toHaveAttribute("data-theme", mode);
        expect(
          (
            await new AxeBuilder({ page })
              .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
              .analyze()
          ).violations,
        ).toEqual([]);
        await page.evaluate(() => scrollTo(0, 0));
        await page.screenshot({
          path: `evidence/board-${size}-${mode}-${locale}.png`,
          fullPage: true,
        });
      });
    }
for (const locale of ["en", "ru"])
  test(`detail ${locale}: prompt, reading, dirty navigation and mobile next step`, async ({
    page,
  }) => {
    const text = catalogs[locale].messages;
    await mock(page, "system", locale);
    await page.goto("/");
    await page
      .getByRole("button", {
        name:
          locale === "en"
            ? "Open Aurora Example: Product engineer"
            : "Открыть Aurora Example: Product engineer",
      })
      .click();
    await expect(
      page.getByRole("article", { name: text["detail.reading"] }),
    ).toBeVisible();
    await expect(page.locator(".document-preview pre")).toHaveAttribute(
      "lang",
      "en",
    );
    await expect(
      page.getByRole("textbox", {
        name: text["detail.documentDraft"].replace(
          "{document}",
          text["slot.message"],
        ),
      }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: text["primary.prepare"], exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText(text["agent.title"]);
    await expect(
      page.getByRole("textbox", { name: text["agent.prompt"] }),
    ).toHaveValue(/case-aurora/);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: text["common.close"], exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: text["primary.prepare"], exact: true }),
    ).toBeFocused();
    await page
      .getByRole("textbox", { name: text["detail.notesLabel"] })
      .fill("Retained fictional local draft");
    await page
      .locator(".sidebar nav")
      .getByRole("button", { name: text["nav.profile"], exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText(text["discard.title"]);
    await page
      .getByRole("button", { name: text["common.keepEditing"] })
      .click();
    await page.getByRole("tab", { name: text["detail.preparation"] }).click();
    await expect(
      page.getByText("How do you connect product decisions to delivery?"),
    ).toBeVisible();
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.screenshot({
      path: `evidence/detail-desktop-${locale}.png`,
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    const next = await page.locator(".next-panel").boundingBox(),
      editor = await page.locator(".editor-pane").boundingBox();
    expect(next!.y).toBeLessThan(editor!.y);
    await expect(
      page.getByRole("textbox", { name: text["detail.notesLabel"] }),
    ).toBeVisible();
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: `evidence/detail-mobile-${locale}.png`,
      fullPage: true,
    });
  });
test("settled search is one board read; detail and Back reuse the overview", async ({
  page,
}) => {
  await mock(page);
  const reads: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/"))
      reads.push(new URL(request.url()).pathname);
  });
  await page.goto("/");
  await expect(page.locator(".stage-strip")).toBeVisible();
  reads.length = 0;
  await page
    .getByRole("textbox", { name: "Search cases" })
    .pressSequentially("Lumen", { delay: 120 });
  await expect
    .poll(() => reads.filter((path) => path === "/api/v1/board").length)
    .toBe(1);
  expect(reads.filter((path) => path === "/api/v1/context")).toHaveLength(0);
  reads.length = 0;
  await page
    .getByRole("button", { name: "Open Aurora Example: Product engineer" })
    .click();
  await expect(
    page.getByRole("article", { name: "Saved document" }),
  ).toBeVisible();
  expect(
    reads.filter((path) => path === "/api/v1/cases/case-aurora"),
  ).toHaveLength(1);
  expect(
    reads.filter(
      (path) => path === "/api/v1/board" || path === "/api/v1/context",
    ),
  ).toHaveLength(0);
  await page.getByRole("button", { name: "Back to cases" }).click();
  await expect(page.locator(".stage-strip")).toBeVisible();
  expect(reads.filter((path) => path === "/api/v1/board")).toHaveLength(0);
});
test("system follows OS while explicit modes, forced colors and zoom remain operable", async ({
  page,
}) => {
  await mock(page);
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.locator(".stage-strip")).toBeVisible();
  const light = await page
    .locator("body")
    .evaluate((node) => getComputedStyle(node).backgroundColor);
  await page.emulateMedia({
    colorScheme: "dark",
    forcedColors: "active",
    reducedMotion: "reduce",
  });
  await expect(page.locator("html")).toHaveAttribute("data-os-theme", "dark");
  await page.emulateMedia({ forcedColors: "none" });
  expect(
    await page
      .locator("body")
      .evaluate((node) => getComputedStyle(node).backgroundColor),
  ).not.toBe(light);
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  await page
    .getByRole("button", { name: "Open Aurora Example: Product engineer" })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Prepare materials with agent",
      exact: true,
    }),
  ).toBeVisible();
});

test("failed locale bootstrap shows recovery and keeps the launch capability in memory", async ({
  page,
}) => {
  await mock(page);
  let failed = true;
  await page.route("**/locales/en.json", (route) =>
    failed ? route.abort() : route.continue(),
  );
  await page.goto("/#launch=fictional-one-use");
  await expect(
    page.getByRole("heading", { name: "Could not open this local workspace." }),
  ).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");
  failed = false;
  await page.getByRole("button", { name: "Retry loading" }).click();
  await expect(page.locator(".stage-strip")).toBeVisible();
});
