import { chromium } from "@playwright/test";
import { execFileSync, spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
const root = process.env.CAREER_BACKEND_ROOT;
const workspace =
  process.env.CAREER_PERF_WORKSPACE ?? "/tmp/career-performance-10000-indexed";
const env = {
  ...process.env,
  CAREER_AGENT_DEVELOPMENT: "1",
  CAREER_AGENT_DEVELOPMENT_ASSETS: join(
    process.cwd(),
    process.env.CAREER_UI_ASSETS ?? "dist",
  ),
  PYTHONDONTWRITEBYTECODE: "1",
};
const cli = (...args) =>
  JSON.parse(
    execFileSync(
      "python3",
      [root + "/scripts/career.py", "--workspace", workspace, ...args],
      { env, encoding: "utf8" },
    ),
  );
const command = (input, revision) =>
  JSON.parse(
    execFileSync(
      "python3",
      [root + "/scripts/career.py", "--workspace", workspace, "command"],
      {
        env,
        encoding: "utf8",
        input: JSON.stringify({
          request_id: randomUUID(),
          expected_revision: revision,
          intent: "case.note",
          input,
        }),
      },
    ),
  );
const first = cli("query", "cases", "--limit", "1").items[0];
const original = cli("query", "case", "--id", first.id).notes;
const launch = cli("ui", "open", "--no-browser");
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CAREER_UI_CHROMIUM,
});
const result = {
  build: launch.release_id,
  workspace,
  total_cases: 10000,
  method:
    "Separate mode=ro SQLite autocommit observer samples workspace.revision every 5ms. Browser requestAnimationFrame samples the visible textarea value and records Date.now(). Difference is DOM observation minus first observed committed revision, excluding CLI startup/plan/backup. Observer lag and browser frame scheduling make this a bounded-resolution diagnostic, not a universal commit-latency percentile.",
  samples: [],
};
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  await page.goto(launch.url);
  await page.locator(`button.card-open[data-case-id="${first.id}"]`).click();
  await page.locator("#private-notes textarea").waitFor();
  for (let sample = 0; sample < 3; sample++) {
    const revision = cli("context").revision,
      expected =
        "Fictional committed visibility probe " + sample + " " + randomUUID();
    const observer = spawn(
      "python3",
      [
        "demo/observe_commit.py",
        join(workspace, "Data/career.sqlite3"),
        String(revision + 1),
      ],
      { env, stdio: ["ignore", "pipe", "pipe"] },
    );
    let buffer = "",
      readyResolve,
      observedResolve,
      observedReject;
    const ready = new Promise((resolve) => (readyResolve = resolve));
    const observed = new Promise((resolve, reject) => {
      observedResolve = resolve;
      observedReject = reject;
    });
    observer.stdout.on("data", (chunk) => {
      buffer += chunk;
      let end;
      while ((end = buffer.indexOf("\n")) >= 0) {
        const line = JSON.parse(buffer.slice(0, end));
        buffer = buffer.slice(end + 1);
        if (line.ready) readyResolve();
        else observedResolve(line);
      }
    });
    observer.on("error", observedReject);
    observer.on("exit", (code) => {
      if (code !== 0)
        observedReject(new Error("Read-only observer failed: " + code));
    });
    await ready;
    await page.evaluate((expected) => {
      window.__careerCommitVisible = null;
      const watch = () => {
        const input = document.querySelector("#private-notes textarea");
        if (input?.value === expected && input.getClientRects().length) {
          window.__careerCommitVisible = {
            observed_ms: Date.now(),
            frame_interval_hint_ms: 1000 / 60,
          };
          return;
        }
        requestAnimationFrame(watch);
      };
      requestAnimationFrame(watch);
    }, expected);
    const commandStart = Date.now();
    command({ case_id: first.id, text: expected }, revision);
    await page.waitForFunction(() => window.__careerCommitVisible !== null);
    const visible = await page.evaluate(() => window.__careerCommitVisible),
      commit = await observed;
    result.samples.push({
      ...commit,
      ...visible,
      observed_commit_to_dom_ms: visible.observed_ms - commit.observed_ns / 1e6,
      cli_invocation_to_observation_ms: visible.observed_ms - commandStart,
      uncertainty:
        "5ms observer interval plus measured SELECT duration; browser frame sampling and 1ms wall-clock precision. Commit may precede first read observation.",
    });
  }
  command({ case_id: first.id, text: original }, cli("context").revision);
  console.log(
    JSON.stringify({
      build: result.build,
      samples: result.samples.map((s) => ({
        observed_commit_to_dom_ms: s.observed_commit_to_dom_ms,
        query_duration_ms: s.query_duration_ns / 1e6,
        cli_invocation_to_observation_ms: s.cli_invocation_to_observation_ms,
      })),
    }),
  );
} finally {
  writeFileSync(
    "evidence/commit-visibility.json",
    JSON.stringify(result, null, 2) + "\n",
  );
  await browser.close();
  cli("ui", "stop", "--no-browser");
}
