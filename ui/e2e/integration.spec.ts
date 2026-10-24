import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
test("real SQLite API: UI/CLI, reload, two tabs, dirty 409, selected packet and polling", async ({
  page,
  browser,
}) => {
  test.skip(
    !process.env.CAREER_BACKEND_ROOT,
    "Set CAREER_BACKEND_ROOT to run actual backend integration.",
  );
  test.setTimeout(120000);
  const root = process.env.CAREER_BACKEND_ROOT!,
    workspace = mkdtempSync(join(tmpdir(), "career-ui-e2e-long-path-")),
    env = {
      ...process.env,
      CAREER_AGENT_DEVELOPMENT: "1",
      CAREER_AGENT_DEVELOPMENT_ASSETS: join(process.cwd(), "dist"),
      PYTHONDONTWRITEBYTECODE: "1",
    };
  const python = process.env.CAREER_PYTHON ?? "python3";
  const cli = (...args: string[]) =>
    JSON.parse(
      execFileSync(
        python,
        [join(root, "scripts/career.py"), "--workspace", workspace, ...args],
        { env, encoding: "utf8" },
      ),
    );
  const command = (intent: string, input: object) => {
    const current = cli("context");
    return JSON.parse(
      execFileSync(
        python,
        [join(root, "scripts/career.py"), "--workspace", workspace, "command"],
        {
          env,
          encoding: "utf8",
          input: JSON.stringify({
            request_id: randomUUID(),
            expected_revision: current.revision,
            intent,
            input,
          }),
        },
      ),
    );
  };
  const fixtureRoot = process.env.CAREER_FIXTURE_ROOT ?? root;
  execFileSync(
    python,
    [
      "-c",
      "import sys,runpy; sys.path.insert(0,sys.argv[1]); import career.facade; fixture=sys.argv[2]; sys.argv=[fixture,sys.argv[3]]; runpy.run_path(fixture,run_name='__main__')",
      join(root, "scripts"),
      join(fixtureRoot, "tests/seed_runtime_1.py"),
      workspace,
    ],
    {
      env,
      encoding: "utf8",
    },
  );
  let second: Awaited<ReturnType<typeof browser.newContext>> | undefined;
  const evidence: {
    workspace: string;
    checks: string[];
    cli_to_visible_ms?: number;
  } = { workspace, checks: [] };
  try {
    const launch = cli("ui", "open", "--no-browser");
    const origin = new URL(launch.url).origin;
    const external: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).origin !== origin)
        external.push(request.url());
    });
    await page.goto(launch.url);
    await expect(
      page.getByRole("button", {
        name: "Open Northstar Demo: Product specialist",
      }),
    ).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    await expect(page.getByText("Live updates connected")).toBeVisible();
    await page
      .getByRole("button", { name: "Open Northstar Demo: Product specialist" })
      .click();
    await expect(page.locator(".detail-heading h1")).toBeFocused();
    await page
      .getByRole("textbox", { name: "Case notes" })
      .fill("Saved from the React UI");
    await page
      .locator("#private-notes")
      .getByRole("button", { name: "Save changes" })
      .click();
    await expect(page.locator("#private-notes")).toContainText(
      "Saved at revision",
    );
    expect(cli("query", "case", "--id", "case_one").notes).toBe(
      "Saved from the React UI",
    );
    evidence.checks.push("UI Save is read back by CLI from SQLite");
    const start = Date.now();
    command("case.note", { case_id: "case_one", text: "External CLI update" });
    await expect(page.getByRole("textbox", { name: "Case notes" })).toHaveValue(
      "External CLI update",
    );
    evidence.cli_to_visible_ms = Date.now() - start;
    evidence.checks.push("CLI commit invalidates selected UI detail via SSE");
    second = await browser.newContext();
    const tab = await second.newPage();
    await tab.goto(cli("ui", "open", "--no-browser").url);
    await tab
      .getByRole("button", { name: "Open Northstar Demo: Product specialist" })
      .click();
    await expect(tab.getByRole("textbox", { name: "Case notes" })).toHaveValue(
      "External CLI update",
    );
    await page
      .getByRole("textbox", { name: "Case notes" })
      .fill("Retained local conflicting draft");
    command("case.note", {
      case_id: "case_one",
      text: "Other writer canonical note",
    });
    await expect(page.getByText(/Saved data changed while/)).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Case notes" })).toHaveValue(
      "Retained local conflicting draft",
    );
    await expect(
      page.getByRole("textbox", { name: "Case notes" }),
    ).toBeFocused();
    await page
      .locator("#private-notes")
      .getByRole("button", { name: "Save changes" })
      .click();
    await expect(page.locator("#private-notes")).toContainText(
      "save conflicts",
    );
    await page
      .getByRole("button", { name: "Keep draft and use current base" })
      .click();
    await page
      .locator("#private-notes")
      .getByRole("button", { name: "Save changes" })
      .click();
    await expect(tab.getByRole("textbox", { name: "Case notes" })).toHaveValue(
      "Retained local conflicting draft",
    );
    evidence.checks.push(
      "Two tabs converge; dirty edit survives external update and real HTTP409",
    );
    const prior = cli("query", "selection", "--id", "packet_one").version_id;
    await page.getByRole("button", { name: /Message Document/ }).click();
    await page.getByRole("option", { name: "Resume", exact: true }).click();
    await page.getByRole("button", { name: "Edit draft" }).click();
    const editor = page.getByRole("textbox", { name: "Resume draft" });
    await editor.fill(
      "Improved processing by 25%.\n\nDraft text edited in the browser.",
    );
    await page
      .locator(".material-content")
      .getByRole("button", { name: "Save changes" })
      .click();
    await expect(page.locator(".material-content")).toContainText(
      "Draft saved; some checks still need attention.",
    );
    await expect(
      page
        .locator(".material-content")
        .getByText("Unsaved changes", { exact: true }),
    ).toHaveCount(0);
    const saved = cli("query", "selection", "--id", "packet_one");
    expect(saved.version_id).not.toBe(prior);
    expect(
      saved.slots.map((slot: { name: string }) => slot.name).sort(),
    ).toEqual(["dossier", "interview", "message", "resume"]);
    expect(saved.assessment.prepared).toBe(false);
    evidence.checks.push(
      "Material edit creates selected immutable draft and requires review",
    );
    await page.reload();
    await page
      .getByRole("button", { name: "Open Northstar Demo: Product specialist" })
      .click();
    await page
      .getByRole("textbox", { name: "Case notes" })
      .fill("Saved after reload");
    await page
      .locator("#private-notes")
      .getByRole("button", { name: "Save changes" })
      .click();
    await expect(page.locator("#private-notes")).toContainText(
      "Saved at revision",
    );
    expect(cli("query", "case", "--id", "case_one").notes).toBe(
      "Saved after reload",
    );
    evidence.checks.push("Reload resumes cookie session and memory CSRF");
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.screenshot({
      path: "evidence/integrated-desktop-light.png",
      fullPage: true,
    });
    await page.route("**/api/v1/events?**", (route) => route.abort());
    await page.reload();
    await page
      .getByRole("button", { name: "Open Northstar Demo: Product specialist" })
      .click();
    command("case.note", {
      case_id: "case_one",
      text: "Fallback polling update",
    });
    await expect(page.getByRole("textbox", { name: "Case notes" })).toHaveValue(
      "Fallback polling update",
      { timeout: 7000 },
    );
    evidence.checks.push("SSE failure falls back to bounded visible polling");
    expect(external).toEqual([]);
    evidence.checks.push("No automatic external requests");
    await page.unroute("**/api/v1/events?**");
    await page
      .locator(".sidebar nav")
      .getByRole("button", { name: "Settings", exact: true })
      .click();
    await page
      .getByRole("button", { name: "English Interface language", exact: true })
      .click();
    await page.getByRole("option", { name: "Русский", exact: true }).click();
    await page
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await expect(page.locator("html")).toHaveAttribute("lang", "ru");
    expect(cli("context").preferences.ui_locale).toBe("ru");
    expect(cli("context").profile.conversation_language).toBe("en");
    await page.reload();
    await page
      .getByRole("button", {
        name: "Открыть Northstar Demo: Product specialist",
      })
      .click();
    const beforePrompt = cli("context").revision;
    await page.locator(".agent-entry").click();
    await expect(
      page.getByRole("textbox", { name: "Промпт для Claude / Codex" }),
    ).toHaveValue(/Работай с установленным пространством/);
    await page.evaluate(() =>
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: async (text: string) => {
            (window as unknown as { copiedPrompt: string }).copiedPrompt = text;
          },
        },
      }),
    );
    await page
      .getByRole("button", { name: "Скопировать промпт", exact: true })
      .click();
    await expect(
      page.getByText("Скопировано. Вставьте промпт в разговор с агентом.", {
        exact: true,
      }),
    ).toBeVisible();
    expect(cli("context").revision).toBe(beforePrompt);
    expect(cli("context").research.status).toBe("paused");
    evidence.checks.push(
      "Canonical RU locale survives reload, document language remains English, localized exact-scope prompt copy performs no command or research",
    );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Закрыть", exact: true })
      .click();
    await page
      .getByRole("button", { name: "К возможностям", exact: true })
      .click();
    const selectedTrack = cli("context").tracks[0];
    await page.locator(".sidebar-tracks button").first().click();
    const scopeResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/v1/agent-intent",
    );
    await page
      .getByRole("button", { name: "Найти возможности", exact: true })
      .click();
    const scoped = await (await scopeResponse).json();
    expect(scoped.descriptor.scope.track_ids).toEqual([selectedTrack.id]);
    await expect(page.locator(".handoff-scope")).toContainText(
      selectedTrack.name,
    );
    expect(cli("context").revision).toBe(beforePrompt);
    expect(cli("context").research.status).toBe("paused");
    evidence.checks.push(
      "Active board track filter binds only that selected track in the actual server descriptor and readable scope; no research executes",
    );
  } finally {
    await second?.close();
    try {
      try {
        cli("ui", "stop", "--no-browser");
      } catch {
        evidence.checks.push(
          "Runtime stop outcome unresolved; no PID kill attempted",
        );
      }
    } finally {
      writeFileSync(
        "evidence/integration.json",
        JSON.stringify(evidence, null, 2),
      );
    }
  }
});
