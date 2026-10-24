import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
const backend = process.env.CAREER_BACKEND_ROOT;
const candidateName = process.env.CAREER_UI_ASSETS ?? "review-candidate-kit4";
const assets = join(process.cwd(), candidateName);
const env = {
  ...process.env,
  CAREER_AGENT_DEVELOPMENT: "1",
  CAREER_AGENT_DEVELOPMENT_ASSETS: assets,
  PYTHONDONTWRITEBYTECODE: "1",
};
const catalogs = Object.fromEntries(
  ["en", "ru"].map((locale) => [
    locale,
    JSON.parse(readFileSync(join(assets, "locales", locale + ".json"), "utf8"))
      .messages,
  ]),
);
const stories = JSON.parse(readFileSync("demo/stories.json", "utf8"));
const manifest = {
  format: "career-agent.screenshots/1",
  fictional: true,
  assets,
  ui_sha256: JSON.parse(
    readFileSync(`evidence/${candidateName}-manifest.json`),
  ).sha256,
  shots: [],
  render_errors: [],
  external_requests: [],
};
mkdirSync("demo-screenshots/readme", { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CAREER_UI_CHROMIUM,
});
try {
  for (const persona of ["designer", "makeup", "analyst", "hospitality"]) {
    const workspace = `/tmp/career-story-${persona}-docs`;
    const cli = (...args) =>
      JSON.parse(
        execFileSync(
          "python3",
          [backend + "/scripts/career.py", "--workspace", workspace, ...args],
          { env, encoding: "utf8" },
        ),
      );
    const command = (input) =>
      JSON.parse(
        execFileSync(
          "python3",
          [backend + "/scripts/career.py", "--workspace", workspace, "command"],
          {
            env,
            encoding: "utf8",
            input: JSON.stringify({
              request_id: randomUUID(),
              expected_revision: cli("context").revision,
              intent: "preferences.set",
              input,
            }),
          },
        ),
      );
    const locale = persona === "designer" || persona === "makeup" ? "ru" : "en";
    command({
      theme: persona === "analyst" ? "dark" : "light",
      ui_locale: locale,
    });
    const launch = cli("ui", "open", "--no-browser");
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
      colorScheme: "light",
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    page.on("pageerror", (error) =>
      manifest.render_errors.push({ persona, error: error.message }),
    );
    page.on("request", (request) => {
      if (new URL(request.url()).origin !== new URL(launch.url).origin)
        manifest.external_requests.push({
          persona,
          path: new URL(request.url()).pathname,
        });
    });
    try {
      await page.goto(launch.url);
      await page.locator(".stage-strip").waitFor();
      const text = () => catalogs[documentLocale];
      let documentLocale = locale;
      async function appearance(ui_locale, theme, system = "light") {
        command({ ui_locale, theme });
        documentLocale = ui_locale;
        await page.emulateMedia({
          colorScheme: system,
          reducedMotion: "reduce",
        });
        await page.waitForFunction(
          ({ ui_locale, theme }) =>
            document.documentElement.lang === ui_locale &&
            document.documentElement.dataset.theme === theme,
          { ui_locale, theme },
        );
      }
      async function shot(
        file,
        screen,
        caption,
        { fullPage = true, primary = false } = {},
      ) {
        await page.evaluate(() => window.scrollTo(0, 0));
        const path = "demo-screenshots/readme/" + file;
        await page.screenshot({ path, fullPage });
        const png = readFileSync(path);
        manifest.shots.push({
          file: path,
          absolute_path: join(process.cwd(), path),
          caption,
          persona: stories[persona].name + " — " + stories[persona].headline,
          screen,
          ui_locale: documentLocale,
          theme: await page.locator("html").getAttribute("data-theme"),
          viewport: page.viewportSize(),
          dimensions: {
            width: png.readUInt32BE(16),
            height: png.readUInt32BE(20),
          },
          source_workspace: workspace,
          build: launch.release_id,
          actual_api: true,
          confirmed_functionality: true,
          primary,
        });
      }
      async function open(index) {
        await page
          .locator(
            `button.card-open[data-case-id="case_${String(index).padStart(2, "0")}"]`,
          )
          .click();
        await page.locator(".detail-heading h1").waitFor();
      }
      async function tab(key) {
        await page.getByRole("tab", { name: text()[key], exact: true }).click();
      }
      async function material(key) {
        await page.locator(".material-toolbar .choice button").click();
        await page
          .getByRole("option", { name: text()[key], exact: true })
          .click();
      }
      if (persona === "designer") {
        const closed = page.getByRole("checkbox", {name:text()["cases.includeClosed"]});
        await closed.focus();
        await page.keyboard.press("Space");
        await page.waitForFunction(() =>
          document
            .querySelector("#column-closed")
            ?.closest("section")
            ?.textContent?.includes("2"),
        );
        await shot(
          "01-designer-board-ru-light.png",
          "board",
          "Fictional designer: twelve shared cases across all six derived stages and two career tracks.",
          { primary: true },
        );
        await appearance("en", "light");
        await page
          .locator(".sidebar nav")
          .getByRole("button", { name: text()["nav.profile"], exact: true })
          .click();
        await page
          .getByRole("heading", { name: text()["profile.title"], exact: true })
          .waitFor();
        await shot(
          "02-designer-profile-en-light.png",
          "profile and career tracks",
          "Fictional designer: one profile, two distinct career directions and separately chosen document languages.",
        );
      } else if (persona === "makeup") {
        await open(4);
        await shot(
          "03-makeup-message-ru-light.png",
          "contact, next step, message and private notes",
          "Fictional makeup artist: relevant professional contact, reviewed personalized message, private notes and a precise next action.",
          { primary: true },
        );
        await appearance("en", "light");
        await material("slot.resume");
        await shot(
          "04-makeup-resume-en-light.png",
          "selected resume",
          "Fictional makeup artist and educator: selected resume retains original sourced contributions and numbers.",
        );
        await material("slot.answers");
        await shot(
          "05-makeup-answers-en-light.png",
          "saved answers and notes",
          "Fictional applicant answers remain scoped; unknown conditions and employer consent are explicit.",
        );
        await appearance("ru", "light");
        await page.locator(".agent-entry").click();
        await page
          .getByRole("textbox", { name: text()["agent.prompt"] })
          .waitFor();
        await shot(
          "06-makeup-agent-prompt-ru.png",
          "scoped agent handoff",
          "Russian agent handoff names the exact case and directions. Copying this editable prompt performs no research, review or sending.",
          { fullPage: false, primary: true },
        );
      } else if (persona === "analyst") {
        await page
          .locator(".view-toggle")
          .getByRole("radio", { name: text()["cases.table"], exact: true })
          .click();
        await page
          .locator('.desktop-case-table button[data-case-id="case_09"]')
          .waitFor();
        await shot(
          "07-analyst-table-en-dark.png",
          "table",
          "Fictional systems and process analyst: bounded table compares people, career tracks, work stages and next actions.",
          { primary: true },
        );
        await page
          .locator('.desktop-case-table button[data-case-id="case_09"]')
          .click();
        await tab("detail.preparation");
        await shot(
          "08-analyst-interview-en-dark.png",
          "saved interview preparation",
          "Fictional analyst interview: saved evidence story, personal attribution, follow-up questions and explicitly simulated logistics.",
          { primary: true },
        );
        await appearance("ru", "dark");
        await tab("detail.history");
        await shot(
          "09-analyst-history-ru-dark.png",
          "history and sources",
          "Fictional reply and interview invitation are explicitly labeled scenario records; history retains the pinned material version and source provenance.",
        );
      } else {
        await page
          .locator(".sidebar nav")
          .getByRole("button", { name: text()["nav.contacts"], exact: true })
          .click();
        await page
          .getByRole("grid", { name: text()["contacts.title"] })
          .waitFor();
        await shot(
          "10-hospitality-contacts-en-light.png",
          "qualified and provisional contacts",
          "Fictional hospitality operations and training: published contacts retain provenance and current-versus-unknown affiliation.",
        );
        await page
          .locator(".sidebar nav")
          .getByRole("button", { name: text()["nav.settings"], exact: true })
          .click();
        await appearance("en", "system");
        await shot(
          "11-settings-en-system.png",
          "theme and interface locale",
          "Canonical system/light/dark appearance and interface language remain separate from conversation and material languages.",
        );
        await appearance("ru", "dark");
        await page
          .locator(".sidebar nav")
          .getByRole("button", { name: new RegExp(text()["nav.cases"]) })
          .click();
        await open(4);
        await page.setViewportSize({ width: 390, height: 844 });
        await shot(
          "12-hospitality-mobile-ru-dark.png",
          "mobile case detail",
          "Fictional hospitality candidate at 390px: person and next action precede the material editor; dark Russian interface.",
          { fullPage: false, primary: true },
        );
      }
    } finally {
      await context.close();
      cli("ui", "stop", "--no-browser");
    }
  }
  if (manifest.render_errors.length || manifest.external_requests.length)
    throw new Error("Screenshot validation failed; inspect manifest.");
  console.log(
    JSON.stringify({
      screenshots: manifest.shots.length,
      primary: manifest.shots.filter((s) => s.primary).map((s) => s.file),
      render_errors: manifest.render_errors.length,
      external_requests: manifest.external_requests.length,
    }),
  );
} catch (error) {
  manifest.capture_error = String(error.message).replace(/#launch=[^\s)]+/g,"#launch=[redacted]");
  console.error(manifest.capture_error);
  process.exitCode = 1;
} finally {
  writeFileSync(
    "demo-screenshots/readme/manifest.json",
    JSON.stringify(manifest, null, 2) + "\n",
  );
  await browser.close();
}
