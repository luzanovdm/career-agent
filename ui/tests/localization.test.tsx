import { documentLanguage } from "../src/app/documentLanguage";
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import ts from "typescript";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { applyLocale, t, type LocaleCatalog } from "../src/app/i18n";
import { Choice, Field } from "../src/ui/controls";
const english = JSON.parse(
  readFileSync("public/locales/en.json", "utf8"),
) as LocaleCatalog;
const russian = JSON.parse(
  readFileSync("public/locales/ru.json", "utf8"),
) as LocaleCatalog;
const placeholders = (value: string) =>
  [...value.matchAll(/\{([a-z_]+)\}/g)].map((match) => match[1]).sort();
describe("complete localization contract", () => {
  it("marks unambiguous configured document language without guessing mixed or missing directions", () => {
    const configured = [
      { id: "design", language: "en" },
      { id: "research", language: "en" },
      { id: "training", language: "ru" },
    ];
    expect(
      documentLanguage([{ id: "design" }, { id: "research" }], configured),
    ).toBe("en");
    expect(
      documentLanguage([{ id: "design" }, { id: "training" }], configured),
    ).toBeUndefined();
    expect(documentLanguage([{ id: "unknown" }], configured)).toBeUndefined();
    expect(documentLanguage([], configured)).toBeUndefined();
  });
  it("ships exact key, placeholder and declared plural coverage in both catalogs", () => {
    expect(Object.keys(russian.messages).sort()).toEqual(
      Object.keys(english.messages).sort(),
    );
    for (const [key, value] of Object.entries(english.messages)) {
      const translated = russian.messages[key];
      expect(typeof translated, key).toBe(typeof value);
      if (typeof value === "string")
        expect(placeholders(translated as string), key).toEqual(
          placeholders(value),
        );
      else {
        expect(Object.keys(translated).sort(), key).toEqual(
          [...russian.plural_categories].sort(),
        );
        for (const text of Object.values(translated))
          expect(placeholders(text), key).toEqual(placeholders(value.other));
      }
    }
  });
  it("uses Russian plural forms, safe text interpolation and English fallback", async () => {
    await applyLocale(russian);
    expect(
      [0, 1, 2, 5, 21].map((count) => t("cases.count", { count })),
    ).toEqual([
      "0 возможностей",
      "1 возможность",
      "2 возможности",
      "5 возможностей",
      "21 возможность",
    ]);
    expect(t("cases.open", { company: "<script>", title: "Пример" })).toBe(
      "Открыть <script>: Пример",
    );
    await applyLocale({
      locale: "fr",
      plural_categories: ["one", "other"],
      messages: { "nav.cases": "Opportunités" },
    });
    expect(t("nav.cases")).toBe("Opportunités");
    expect(t("common.save")).toBe("Save changes");
    await applyLocale(english);
  });
  it("connects help to fields and gives selectors one label", () => {
    render(
      <>
        <Field
          label="Fictional field"
          description="Consequential help"
          value=""
          onChange={() => {}}
        />
        <Choice
          label="Fictional choice"
          value="en"
          onChange={() => {}}
          options={[{ id: "en", name: "English" }]}
        />
      </>,
    );
    expect(
      screen.getByRole("textbox", { name: "Fictional field" }),
    ).toHaveAccessibleDescription("Consequential help");
    expect(
      screen.getByRole("button", { name: /English Fictional choice/ }),
    ).toHaveAccessibleName("English Fictional choice");
  });
  it("keeps visible JSX text and labels behind translation keys", () => {
    const files = (directory: string): string[] =>
      readdirSync(directory, { withFileTypes: true }).flatMap((item) =>
        item.isDirectory()
          ? files(join(directory, item.name))
          : item.name.endsWith(".tsx")
            ? [join(directory, item.name)]
            : [],
      );
    const literals: string[] = [];
    for (const file of files("src")) {
      const source = ts.createSourceFile(
        file,
        readFileSync(file, "utf8"),
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      );
      const visit = (node: ts.Node) => {
        if (
          ts.isJsxText(node) &&
          /[A-Za-zА-Яа-я]/.test(node.text) &&
          node.text.trim() !== "CA"
        )
          literals.push(file + ": " + node.text.trim());
        if (
          ts.isJsxAttribute(node) &&
          ["label", "description", "aria-label", "title"].includes(
            node.name.getText(source),
          ) &&
          node.initializer &&
          ts.isStringLiteral(node.initializer) &&
          /[A-Za-zА-Яа-я]/.test(node.initializer.text)
        )
          literals.push(file + ": " + node.initializer.text);
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(literals).toEqual([]);
  });
});
