import { describe, it, expect, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { applyLocale } from "../src/app/i18n";
import { RouteIdentity, RouteLink } from "../src/features/CaseRoute";
import { CaseCard, Cases } from "../src/features/Cases";
import { Detail } from "../src/features/Detail";
import { Api } from "../src/api/client";
import type { CaseSummary } from "../src/api/types";
import { caseItem, detail, page } from "./fixtures";

const english = JSON.parse(readFileSync("public/locales/en.json", "utf8"));
const russian = JSON.parse(readFileSync("public/locales/ru.json", "utf8"));
afterEach(async () => {
  await applyLocale(english);
});
function view(item: CaseSummary) {
  return render(
    <>
      <RouteIdentity item={item} />
      <RouteLink item={item} />
    </>,
  );
}
const mailbox: CaseSummary = {
  ...caseItem,
  route: "company",
  contact: null,
  selected_route: {
    owner: "company",
    kind: "email",
    value: "projects@aurora.example",
    source_id: "source_public",
    qualified: true,
  },
};

describe("canonical company, person and form route display", () => {
  it("uses the shared mailbox identity in the actual detail and table consumers", () => {
    const result = render(
      <Detail
        detail={{ ...detail, case: mailbox }}
        api={new Api()}
        onDirty={() => {}}
        refresh={() => {}}
        onPacket={() => {}}
      />,
    );
    expect(
      screen.getByRole("link", { name: "projects@aurora.example" }),
    ).toHaveAttribute("href", "mailto:projects@aurora.example");
    expect(
      screen.queryByText(/Contact not selected|Person route|Form fallback/),
    ).not.toBeInTheDocument();
    result.unmount();
    render(
      <Cases
        pages={{ table: { ...page(), items: [mailbox] } }}
        view="table"
        selected={null}
        onSelect={() => {}}
        onMore={() => {}}
        pending={false}
      />,
    );
    const table = within(document.querySelector(".desktop-case-table")!);
    expect(table.getByText("projects@aurora.example")).toBeInTheDocument();
    expect(table.getByText(/Company mailbox/)).toBeInTheDocument();
  });
  it("shows a company mailbox without inventing a person or calling it a form", () => {
    view(mailbox);
    expect(screen.getByText(/Company mailbox/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "projects@aurora.example" }),
    ).toHaveAttribute("href", "mailto:projects@aurora.example");
    expect(screen.getByText(/Route verified/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Contact not selected|Person route|Form fallback/),
    ).not.toBeInTheDocument();
  });
  it("keeps a real person's name and email distinct", () => {
    view({
      ...caseItem,
      selected_route: {
        owner: "person",
        kind: "email",
        value: "jordan@aurora.example",
        qualified: true,
      },
    });
    expect(screen.getByText("Jordan Example")).toBeInTheDocument();
    expect(screen.getByText(/Person route/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "jordan@aurora.example" }),
    ).toHaveAttribute("href", "mailto:jordan@aurora.example");
    expect(screen.queryByText("Company mailbox")).not.toBeInTheDocument();
  });
  it("keeps a form tied to its actual HTTP locator", () => {
    view({
      ...caseItem,
      route: "form",
      contact: null,
      selected_route: {
        owner: "case",
        kind: "form",
        value: "https://aurora.example/jobs/42",
        qualified: true,
      },
    });
    expect(screen.getByText("Application form")).toBeInTheDocument();
    expect(screen.getByText(/Form fallback/)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://aurora.example/jobs/42",
    );
  });
  it("shows missing and unsupported routes honestly without using a stale mailbox", () => {
    for (const route of ["unknown", "unsupported"] as CaseSummary["route"][]) {
      const result = view({ ...mailbox, route });
      expect(screen.getByText("No selected route")).toBeInTheDocument();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      result.unmount();
    }
    view({ ...mailbox, selected_route: null });
    expect(
      screen.getByText("Company mailbox not selected"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("never upgrades an unqualified or unsafe mailbox into a verified link", () => {
    const result = view({
      ...mailbox,
      selected_route: { ...mailbox.selected_route!, qualified: false },
    });
    expect(screen.getByText(/Route needs verification/)).toBeInTheDocument();
    result.unmount();
    view({
      ...mailbox,
      selected_route: {
        ...mailbox.selected_route!,
        value: "projects@aurora.example?bcc=other@example.com",
      },
    });
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText(/Route needs verification/)).toBeInTheDocument();
  });
  it("uses the same mailbox identity on a board card and Russian locale", async () => {
    await applyLocale(russian);
    render(<CaseCard item={mailbox} selected={false} onSelect={() => {}} />);
    expect(screen.getByText("projects@aurora.example")).toBeInTheDocument();
    expect(screen.getByText(/Почта компании/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Контакт не выбран|Через человека|Резервный вариант/),
    ).not.toBeInTheDocument();
  });
});
