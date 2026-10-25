import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
test("actual bounded profile/context, sources, versions/sent pins, retained history and exports", async ({
  page,
}) => {
  test.skip(
    !process.env.CAREER_BACKEND_ROOT,
    "Requires isolated runtime fixture",
  );
  test.setTimeout(180000);
  page.setDefaultTimeout(10000);
  const root = process.env.CAREER_BACKEND_ROOT!,
    workspace = mkdtempSync("/tmp/career-coverage-");
  const python = process.env.CAREER_PYTHON ?? "python3",
    env = {
      ...process.env,
      CAREER_AGENT_DEVELOPMENT: "1",
      CAREER_AGENT_DEVELOPMENT_ASSETS: join(process.cwd(), "dist"),
      PYTHONDONTWRITEBYTECODE: "1",
    };
  const cli = (...args: string[]) =>
    JSON.parse(
      execFileSync(
        python,
        [join(root, "scripts/career.py"), "--workspace", workspace, ...args],
        { env, encoding: "utf8" },
      ),
    );
  const command = (intent: string, input: object) => {
    try {
      return JSON.parse(
        execFileSync(
          python,
          [
            join(root, "scripts/career.py"),
            "--workspace",
            workspace,
            "command",
          ],
          {
            env,
            encoding: "utf8",
            input: JSON.stringify({
              request_id: randomUUID(),
              expected_revision: cli("context").revision,
              intent,
              input,
            }),
          },
        ),
      );
    } catch (error) {
      const e = error as { status: number; stdout: string };
      if (e.status === 3) {
        const value = JSON.parse(e.stdout);
        if (value.outcome === "partial") return value;
      }
      throw error;
    }
  };
  execFileSync(python, [join(root, "tests/seed_runtime_1.py"), workspace], {
    env,
    encoding: "utf8",
  });
  const prior = cli("query", "selection", "--id", "packet_one");
  command("activity.record", {
    case_id: "case_one",
    kind: "sent",
    occurred_at: "2026-10-24T12:00:00Z",
    evidence: "Fictional pinned send",
    packet_id: "packet_one",
    version_id: prior.version_id,
  });
  command("packet.save", {
    packet_id: "packet_one",
    used_claim_ids: ["claim_one"],
    documents: [
      { slot: "resume", text: "Improved processing by 25%." },
      { slot: "message", text: "Current fictional message" },
      { slot: "dossier", text: "Private current dossier" },
      { slot: "interview", text: "Unstructured saved preparation document." },
    ],
  });
  for (let n = 0; n < 27; n++)
    command("claim.save", {
      id: `claim_extra_${String(n).padStart(2, "0")}`,
      assertion: `Fictional evidence statement ${String.fromCharCode(65 + (n % 26))}`,
      meaning: "Supported private project contribution",
      source_ids: ["source_one"],
      confirmation: "unknown",
      disclosure: "private",
    });
  command("answer.save", {
    id: "answer_pending",
    meaning: "availability.start",
    scope: { track_id: "track_one" },
    units: { duration: "weeks" },
    disposition: "pending",
    value: null,
    evidence: "Open fictional question: when is a start possible?",
    response_state: "pending",
  });
  command("answer.save", {
    id: "answer_unknown",
    meaning: "work.mode",
    scope: { track_id: "track_one" },
    units: {},
    disposition: "unknown",
    value: null,
    evidence: "The fictional user explicitly does not know.",
    response_state: "provided",
  });
  command("answer.save", {
    id: "answer_context",
    meaning: "case.private_context",
    scope: { case_id: "case_one" },
    units: {},
    disposition: "answered",
    value: {
      current_assessment: "Conditional fictional role context",
      current_next_action: "Ask the evidenced colleague about workflow.",
    },
    evidence: "Fictional private assessment",
  });
  command("answer.save", {
    id: "answer_timeline",
    meaning: "profile.timeline",
    scope: { purpose: "profile" },
    units: {},
    disposition: "answered",
    value: {
      start_date: "2020",
      end_date: "2023",
      role: "Fictional contributor",
      employer: "Fictional Example",
    },
    evidence: "Fictional supplied timeline",
  });
  command("answer.save", {
    id: "answer_master",
    meaning: "profile.master_resume",
    scope: { purpose: "profile" },
    units: {},
    disposition: "answered",
    value: {
      artifact_id: prior.slots.find(
        (slot: { name: string }) => slot.name === "resume",
      ).artifact_id,
    },
    evidence: "Fictional exact original resume binding",
  });
  cli("render", "--format", "csv");
  command("case.note", {
    case_id: "case_one",
    text: "A later fictional business revision makes the CSV stale.",
  });
  // Imported immutable observations and an original null pin are fixture inputs, not new-send API commands.
  execFileSync(
    python,
    [
      "-c",
      `import sys,json;sys.path.insert(0,sys.argv[1]+'/scripts');sys.path.insert(0,sys.argv[1]+'/maintenance');from career.repository import Repository;from project_history import prepare_projection;repo=Repository(sys.argv[2]);db=repo.connect();rows=[dict(employer='Harbor Example',role='Historical role',status='sent',event_kind='sent',evidence_level='user_reported',date_text='October 2026',date_precision='approximate',evidence='Fictional unlinked observation'),dict(employer='Delta Example',status='uncertain',event_kind='sent',evidence_level='user_reported',date_precision='unknown')];[(db.execute('INSERT INTO record_history(kind,record_id,version,body,revision) VALUES (?,?,?,?,0)',('legacy:history_imports',str(i),1,json.dumps(row)))) for i,row in enumerate(rows)];db.execute('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)',('history_unknown','case_one','sent','2026-10-23T12:00:00Z','2026-10-24T12:00:00Z','Fictional retained unknown historical attachment',None,None,None,'{}'));db.close();repo.cache_historical_observations(prepare_projection(repo))`,
      root,
      workspace,
    ],
    { env, encoding: "utf8" },
  );
  const baseline = cli("query", "case", "--id", "case_one"),
    start = cli("context").revision;
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    const launch = cli("ui", "open", "--no-browser"),
      origin = new URL(launch.url).origin;
    const external: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).origin !== origin)
        external.push(request.url());
    });
    await page.goto(launch.url);
    await page
      .locator(".sidebar nav")
      .getByRole("button", { name: "Profile & tracks", exact: true })
      .click();
    const bank = page.locator(".evidence-bank");
    await expect(bank.locator(".evidence-record")).toHaveCount(25);
    await bank.getByRole("button", { name: "Load more saved records" }).click();
    await expect(bank.locator(".evidence-record")).toHaveCount(28);
    await bank.locator(".source-evidence button").first().click();
    await expect(bank).toContainText("Morgan Example leads the product team.");
    await bank.getByRole("tab", { name: "Answers and open questions" }).click();
    await expect(bank).toContainText("Open fictional question");
    await expect(bank).toContainText(
      "The fictional user explicitly does not know",
    );
    await expect(bank).toContainText("Fictional contributor");
    await expect(
      bank.getByRole("link", { name: /Download saved original/ }),
    ).toHaveCount(1);
    const retained = page.locator(".retained-history");
    await expect(retained).toContainText("Harbor Example");
    await expect(retained).toContainText("Delta Example");
    await expect(retained).toContainText("October 2026");
    const track = page.locator(".tracks .panel").first();
    await track.getByRole("button", { name: "Edit", exact: true }).click();
    await track
      .getByRole("textbox", { name: "Positioning" })
      .fill("Edited supported track positioning");
    await track
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await expect(track).toContainText("Edited supported track positioning");
    const changed = cli("context");
    expect(changed.tracks[0].claim_ids).toEqual(["claim_one"]);
    expect(changed.tracks[0].policies).toEqual({});
    await page.screenshot({
      path: "evidence/coverage-profile-desktop.png",
      fullPage: true,
    });
    await page
      .locator(".sidebar nav")
      .getByRole("button", { name: /^Cases/ })
      .click();
    await page
      .getByRole("button", { name: "Open Northstar Demo: Product specialist" })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "Current fictional message",
    );
    await page
      .getByRole("tab", { name: "Saved case context", exact: true })
      .click();
    await page
      .locator(".evidence-bank")
      .getByRole("tab", { name: "Answers and open questions" })
      .click();
    await expect(page.locator(".evidence-bank")).toContainText(
      "Conditional fictional role context",
    );
    await page
      .getByRole("tab", { name: "History & sources", exact: true })
      .click();
    await expect(page.locator("main")).toContainText(
      "Sent; historical attachment is unknown.",
    );
    await page
      .getByRole("button", { name: "Open exact saved materials", exact: true })
      .click();
    await expect(page.locator(".document-preview")).toContainText(
      "A relevant workflow contribution.",
    );
    await expect(page.locator("main")).toContainText(
      "Historical version — read-only.",
    );
    await expect(
      page.getByRole("button", { name: "Edit draft", exact: true }),
    ).not.toBeVisible();
    await page
      .getByRole("button", { name: "Browse saved versions", exact: true })
      .click();
    await page.getByRole("button", { name: /Version to view$/ }).click();
    await page.getByRole("option", { name: /Currently selected/ }).click();
    await expect(page.locator(".document-preview")).toContainText(
      "Current fictional message",
    );
    const result = cli("query", "case", "--id", "case_one");
    expect(result.selection.version_id).toBe(baseline.selection.version_id);
    expect(result.history).toEqual(baseline.history);
    expect(cli("context").revision).toBe(start + 1);
    await page
      .getByRole("button", {
        name: "Static exports are out of date",
        exact: true,
      })
      .click();
    const link = page.getByRole("link", {
      name: "Download Cases.csv",
      exact: true,
    });
    await expect(link).toBeVisible();
    const downloadUrl = new URL((await link.getAttribute("href"))!, page.url());
    expect(downloadUrl.origin).toBe(origin);
    const downloaded = await page.request.get(downloadUrl.href);
    expect(downloaded.status()).toBe(200);
    expect(await downloaded.text()).toContain("Northstar Demo");
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.screenshot({
      path: "evidence/coverage-history-desktop.png",
      fullPage: true,
    });
    expect(errors).toEqual([]);
    expect(external).toEqual([]);
    writeFileSync(
      "evidence/data-coverage.json",
      JSON.stringify(
        {
          workspace,
          passed: true,
          profile_claims: 28,
          answers: 5,
          retained_observations: 2,
          navigation_business_writes: 0,
          track_command_writes: 1,
          primary_unchanged: true,
          sent_pins_unchanged: true,
          render_errors: errors,
          external_requests: external,
        },
        null,
        2,
      ),
    );
  } finally {
    expect(cli("ui", "stop", "--no-browser").status).toBe("stopped");
  }
});
