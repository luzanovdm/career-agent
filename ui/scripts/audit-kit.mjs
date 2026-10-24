import ts from "typescript";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const files = (directory) =>
  readdirSync(directory, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? files(join(directory, entry.name))
      : entry.name.endsWith(".tsx")
        ? [join(directory, entry.name)]
        : [],
  );
const inventory = {
  native_controls: [],
  native_tooltips: [],
  custom_interaction_handlers: [],
  direct_library_imports: [],
  components: {},
};
const native = new Set([
  "button",
  "a",
  "input",
  "select",
  "textarea",
  "details",
  "summary",
  "dialog",
  "menu",
]);
for (const file of files("src")) {
  const source = ts.createSourceFile(
    file,
    readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const at = (node) => ({
    file,
    line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
  });
  function walk(node) {
    if (
      ts.isImportDeclaration(node) &&
      node.moduleSpecifier.text === "react-aria-components"
    )
      inventory.direct_library_imports.push(at(node));
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const name = node.tagName.getText(source);
      inventory.components[name] = (inventory.components[name] ?? 0) + 1;
      if (native.has(name))
        inventory.native_controls.push({ ...at(node), tag: name });
      if (
        name[0] === name[0].toLowerCase() &&
        node.attributes.properties.some(
          (attribute) =>
            ts.isJsxAttribute(attribute) &&
            [
              "onClick",
              "onKeyDown",
              "onPointerDown",
              "onMouseDown",
              "onTouchStart",
            ].includes(attribute.name.getText(source)),
        )
      )
        inventory.custom_interaction_handlers.push({ ...at(node), tag: name });
      if (
        name[0] === name[0].toLowerCase() &&
        node.attributes.properties.some(
          (attribute) =>
            ts.isJsxAttribute(attribute) &&
            attribute.name.getText(source) === "role" &&
            attribute.initializer &&
            ts.isStringLiteral(attribute.initializer) &&
            [
              "button",
              "checkbox",
              "switch",
              "tab",
              "option",
              "menuitem",
              "combobox",
            ].includes(attribute.initializer.text),
        )
      )
        inventory.custom_interaction_handlers.push({
          ...at(node),
          tag: name,
          kind: "interactive-role",
        });
      if (
        node.attributes.properties.some(
          (attribute) =>
            ts.isJsxAttribute(attribute) &&
            attribute.name.getText(source) === "title",
        ) &&
        name[0] === name[0].toLowerCase()
      )
        inventory.native_tooltips.push(at(node));
    }
    ts.forEachChild(node, walk);
  }
  walk(source);
}
inventory.passed =
  inventory.native_controls.length === 0 &&
  inventory.native_tooltips.length === 0 &&
  inventory.custom_interaction_handlers.length === 0 &&
  inventory.direct_library_imports.every(
    (item) => item.file === "src/ui/controls.tsx",
  );
writeFileSync(
  "evidence/ui-kit-inventory.json",
  JSON.stringify(inventory, null, 2) + "\n",
);
console.log(JSON.stringify(inventory, null, 2));
if (!inventory.passed) process.exitCode = 1;
