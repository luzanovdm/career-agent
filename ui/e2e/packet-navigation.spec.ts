import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID, createHash } from "node:crypto";

test("actual saved alternatives: case/person navigation, exact bytes, reopen, dirty guards and stale exports", async ({
  page,
}) => {
  test.skip(
    !process.env.CAREER_BACKEND_ROOT,
    "Requires the isolated backend fixture.",
  );
  test.setTimeout(120000);
  const root = process.env.CAREER_BACKEND_ROOT!;
  const workspace = mkdtempSync("/tmp/career-packet-navigation-");
  const env = {
    ...process.env,
    CAREER_AGENT_DEVELOPMENT: "1",
    CAREER_AGENT_DEVELOPMENT_ASSETS: join(process.cwd(), "dist"),
    PYTHONDONTWRITEBYTECODE: "1",
  };
  const cli = (...args: string[]) =>
    JSON.parse(
      execFileSync(
        process.env.CAREER_PYTHON ?? "python3",
        [join(root, "scripts/career.py"), "--workspace", workspace, ...args],
        { env, encoding: "utf8" },
      ),
    );
  const command = (intent: string, input: object) => {
    const args = [
      join(root, "scripts/career.py"),
      "--workspace",
      workspace,
      "command",
    ];
    const options = {
      env,
      encoding: "utf8" as const,
      input: JSON.stringify({
        request_id: randomUUID(),
        expected_revision: cli("context").revision,
        intent,
        input,
      }),
    };
    try {
      return JSON.parse(
        execFileSync(process.env.CAREER_PYTHON ?? "python3", args, options),
      );
    } catch (error) {
      const failed = error as { status: number; stdout: string };
      if (failed.status === 3) {
        const receipt = JSON.parse(failed.stdout);
        if (receipt.outcome === "partial") return receipt;
      }
      throw error;
    }
  };
  execFileSync(
    process.env.CAREER_PYTHON ?? "python3",
    [join(root, "tests/seed_runtime_1.py"), workspace],
    { env, encoding: "utf8" },
  );
  cli("render", "--format", "csv");
  const original = cli("query", "case", "--id", "case_one");
  command("activity.record", {
    case_id: "case_one",
    kind: "sent",
    occurred_at: "2026-10-24T12:00:00Z",
    evidence: "Explicit fictional manually reported history",
    packet_id: "packet_one",
    version_id: original.selection.version_id,
  });
  command("contact.capture", {
    id: "person_two",
    name: "Taylor Example",
    company_id: "company_one",
    affiliation: "current",
    relevance: "Fictional process colleague",
    sources: [
      {
        source_id: "source_one",
        axes: ["identity", "affiliation", "relevance"],
        assessment: "supports",
      },
    ],
    route: {
      kind: "profile",
      value: "https://northstar.example/taylor",
      source_id: "source_one",
    },
  });
  const external: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    const launch = cli("ui", "open", "--no-browser");
    const origin = new URL(launch.url).origin;
    page.on("request", (request) => {
      if (new URL(request.url()).origin !== origin)
        external.push(request.url());
    });
    await page.goto(launch.url);
    await expect(
      page.getByRole("button", { name: "Static exports are out of date" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Open Northstar Demo: Product specialist" })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "A relevant workflow contribution.",
    );
    command("source.capture", {
      id: "source_term",
      locator: "https://workflow.example/terms",
      excerpt: "A fictional observed workflow definition.",
      observed_at: "2026-10-24T00:00:00Z",
      readable: true,
    });
    for (const [id, person] of [
      ["contact_a", "person_one"],
      ["contact_b", "person_two"],
    ]) {
      command("packet.create", {
        id,
        case_id: "case_one",
        person_id: person,
        purpose: "contact",
      });
      command("packet.save", {
        packet_id: id,
        used_claim_ids: [],
        documents: [
          { slot: "message", text: `Exact fictional message ${id}` },
          {
            slot: "interview",
            text: JSON.stringify({
              format: "career-agent.interview/1",
              turns: [
                {
                  kind: "question",
                  text: "What did you improve?",
                  status: "hypothesis",
                  source_ids: [],
                  terms: [],
                },
                {
                  kind: "answer",
                  text: `Private preparation ${id}. Workflow`,
                  status: "outline",
                  source_ids: ["source_term"],
                  terms: [
                    {
                      label: "Workflow",
                      url: "https://workflow.example/terms",
                      source_id: "source_term",
                    },
                  ],
                },
              ],
            }),
          },
        ],
      });
    }
    const baseline = cli("query", "case", "--id", "case_one");
    const revision = cli("context").revision;
    const picker = () => page.getByRole("button", { name: /Saved packet$/ });
    await picker().click();
    await expect(
      page.getByRole("option", { name: /Contact message · Taylor Example/ }),
    ).toBeVisible();
    await page
      .getByRole("option", { name: /Contact message · Taylor Example/ })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "Exact fictional message contact_b",
    );
    await expect(page.locator(".case-context")).toContainText(
      "Case primary route",
    );
    await expect(
      page.getByText(
        "No sent event is linked to this saved version. Opening it performs no transmission.",
      ),
    ).toBeVisible();
    await page
      .getByRole("tab", { name: "Interview preparation", exact: true })
      .click();
    await expect(page.locator(".interview")).toContainText(
      "Private preparation contact_b",
    );
    await expect(page.locator(".dialogue .question")).toContainText(
      "What did you improve?",
    );
    await expect(
      page.locator(".dialogue .answer").getByRole("link", { name: "Workflow" }),
    ).toHaveAttribute("href", "https://workflow.example/terms");
    await page.getByRole("tab", { name: "Materials", exact: true }).click();
    await page
      .getByRole("button", { name: "Saved version", exact: true })
      .click();
    const saved = cli("query", "selection", "--id", "contact_b");
    expect(
      saved.slots.find((slot: { name: string }) => slot.name === "message")
        .sha256,
    ).toBe(
      createHash("sha256")
        .update("Exact fictional message contact_b")
        .digest("hex"),
    );
    await expect(page.locator(".document-meta")).toContainText(
      saved.slots.find((slot: { name: string }) => slot.name === "message")
        .sha256,
    );
    await page.getByRole("button", { name: "Edit draft", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Message draft" })
      .fill("Unsaved fictional local edit");
    await picker().click();
    await page
      .getByRole("option", { name: /Application · Morgan Example/ })
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page
      .getByRole("button", { name: "Keep editing", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Message draft" }),
    ).toHaveValue("Unsaved fictional local edit");
    await page
      .locator(".material-content")
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    await picker().click();
    await page
      .getByRole("option", { name: /Application · Morgan Example/ })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "A relevant workflow contribution.",
    );
    await page
      .getByRole("button", { name: "Back to cases", exact: true })
      .click();
    await page
      .locator(".sidebar nav")
      .getByRole("button", { name: "Contacts", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Taylor Example", exact: true })
      .click();
    await page
      .locator(".contact-packets")
      .getByRole("button", { name: /Contact message · Taylor Example/ })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "Exact fictional message contact_b",
    );
    await page
      .getByRole("button", { name: "Back to contacts", exact: true })
      .click();
    await expect(page.locator(".contact-packets")).toContainText(
      "Taylor Example",
    );
    await page
      .locator(".contact-packets")
      .getByRole("button", { name: /Contact message · Taylor Example/ })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "Exact fictional message contact_b",
    );
    expect(cli("context").revision).toBe(revision);
    let after = cli("query", "case", "--id", "case_one");
    expect(after.selection).toEqual(baseline.selection);
    expect(after.history).toEqual(baseline.history);
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.screenshot({
      path: "evidence/packet-navigation-desktop-en.png",
      fullPage: true,
    });
    command("case.close", {
      case_id: "case_one",
      reason: "Fictional close",
      evidence: "Fictional decision",
    });
    await expect(page.locator(".case-context")).toContainText("Closed");
    await expect(page.locator(".document-preview")).toContainText(
      "Exact fictional message contact_b",
    );
    command("case.reopen", { case_id: "case_one", reason: "Fictional reopen" });
    command("preferences.set", { ui_locale: "ru", theme: "dark" });
    await expect(page.locator("html")).toHaveAttribute("lang", "ru");
    await expect(page.locator(".document-preview")).toContainText(
      "Exact fictional message contact_b",
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("button", { name: /Сохранённый пакет$/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Статические экспорты устарели" }),
    ).toBeVisible();
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.screenshot({
      path: "evidence/packet-navigation-mobile-ru.png",
      fullPage: true,
    });
    await page.reload();
    await page
      .locator(".mobile-nav")
      .getByRole("button", { name: "Контакты", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Taylor Example", exact: true })
      .click();
    await page
      .locator(".contact-packets")
      .getByRole("button", { name: /Сообщение контакту · Taylor Example/ })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "Exact fictional message contact_b",
    );
    after = cli("query", "case", "--id", "case_one");
    expect(after.selection).toEqual(baseline.selection);
    expect(after.history).toEqual(baseline.history);
    expect(cli("context").research.status).toBe("paused");
    expect(external).toEqual([]);
    expect(errors).toEqual([]);
    writeFileSync(
      "evidence/packet-navigation.json",
      JSON.stringify(
        {
          workspace,
          passed: true,
          primary_unchanged: true,
          history_unchanged: true,
          navigation_business_writes: 0,
          external_requests: external,
          render_errors: errors,
          selected_hash: saved.slots[0].sha256,
        },
        null,
        2,
      ),
    );
  } finally {
    const stopped = cli("ui", "stop", "--no-browser");
    expect(stopped.status).toBe("stopped");
  }
});
