import { useState } from "react";
import {
  Table,
  TableHeader,
  TableBody,
  Column as TableColumn,
  Row,
  Cell,
} from "../ui/controls";
import {
  columns,
  type CasePage,
  type CaseSummary,
  type Column,
} from "../api/types";
import { t, issueText } from "../app/i18n";
import { RouteIdentity } from "./CaseRoute";
import {
  Button,
  Check,
  Hint,
  GridList,
  GridListItem,
  ToggleButtonGroup,
  ToggleButton,
} from "../ui/controls";
export function CaseCard({
  item,
  selected,
  onSelect,
  showStage = false,
}: {
  item: CaseSummary;
  selected: boolean;
  onSelect: (id: string) => void;
  showStage?: boolean;
}) {
  return (
    <article className={`case-card ${selected ? "selected" : ""}`}>
      <Button
        className="card-open"
        data-case-id={item.id}
        onPress={() => onSelect(item.id)}
        aria-label={t("cases.open", {
          company: item.company,
          title: item.title,
        })}
      >
        <span className="card-company">{item.company}</span>
        <strong>{item.title}</strong>
      </Button>
      <p className="card-person">
        <RouteIdentity item={item} />
      </p>
      <div className="tags">
        {showStage && (
          <span className="tag stage-tag">{t(`column.${item.column}`)}</span>
        )}
        {item.tracks.map((track) => (
          <Hint key={track.id} text={track.rationale}>
            {track.name}
          </Hint>
        ))}
        {item.kind !== "vacancy" && (
          <span className="tag">{t(`cases.${item.kind}`)}</span>
        )}
      </div>
      <p className="next-action">{t(`next.${item.column}`)}</p>
      {item.blockers.length > 0 && (
        <p className="blocker">
          {t("cases.needsAttention", { issue: issueText(item.blockers[0]) })}
        </p>
      )}
    </article>
  );
}
export function Cases({
  pages,
  view,
  selected,
  onSelect,
  onMore,
  pending,
  onClear,
}: {
  pages: Record<string, CasePage>;
  view: "board" | "table";
  selected: string | null;
  onSelect: (id: string) => void;
  onMore: (key: string) => void;
  pending: boolean;
  onClear?: () => void;
}) {
  const [hideEmpty, setHideEmpty] = useState(true),
    [active, setActive] = useState<Column | null>(null);
  const first = pages.table ?? pages.qualify,
    total = first?.counts.total;
  if (total === 0)
    return (
      <div className="empty-state">
        <h2>{t("cases.empty")}</h2>
        <p>{t("cases.emptyHint")}</p>
        {onClear && (
          <Button onPress={onClear}>{t("cases.clearFilters")}</Button>
        )}
      </div>
    );
  if (view === "table") {
    const page = pages.table;
    return (
      <>
        <GridList
          className="narrow-case-list"
          aria-label={t("cases.title")}
          items={page?.items ?? []}
        >
          {(item) => (
            <GridListItem
              id={item.id}
              textValue={`${item.company} ${item.title}`}
              onAction={() => onSelect(item.id)}
            >
              <CaseCard
                item={item}
                selected={selected === item.id}
                onSelect={onSelect}
                showStage
              />
            </GridListItem>
          )}
        </GridList>
        <div className="table-wrap desktop-case-table">
          <Table
            aria-label={t("cases.title")}
            selectionMode="single"
            selectedKeys={selected ? [selected] : []}
            onRowAction={(key) => onSelect(String(key))}
          >
            <TableHeader>
              <TableColumn isRowHeader>{t("cases.companyRole")}</TableColumn>
              <TableColumn>{t("cases.tracksContact")}</TableColumn>
              <TableColumn>{t("cases.nextWork")}</TableColumn>
              <TableColumn>{t("cases.nextAction")}</TableColumn>
            </TableHeader>
            <TableBody
              items={page?.items ?? []}
              renderEmptyState={() => t("cases.empty")}
            >
              {(item) => (
                <Row id={item.id}>
                  <Cell>
                    <Button
                      className="table-open"
                      data-case-id={item.id}
                      onPress={() => onSelect(item.id)}
                    >
                      {item.company}
                      <strong>{item.title}</strong>
                    </Button>
                    <small>{t(`cases.${item.kind}`)}</small>
                  </Cell>
                  <Cell>
                    <RouteIdentity item={item} />
                    <small>
                      {item.tracks.map((track) => track.name).join(", ")}
                    </small>
                  </Cell>
                  <Cell>{t(`column.${item.column}`)}</Cell>
                  <Cell>
                    {t(`next.${item.column}`)}
                    {item.blockers.map((issue, index) => (
                      <small key={index}>{issueText(issue)}</small>
                    ))}
                  </Cell>
                </Row>
              )}
            </TableBody>
          </Table>
        </div>
        {page?.next_cursor && (
          <Button
            className="load-more"
            isDisabled={pending}
            onPress={() => onMore("table")}
          >
            {t("cases.more")}
          </Button>
        )}
      </>
    );
  }
  const current =
    active ??
    columns.find(
      (column) => (pages[column]?.counts.columns[column] ?? 0) > 0,
    ) ??
    "qualify";
  return (
    <>
      <ToggleButtonGroup
        className="stage-strip"
        aria-label={t("cases.stagePicker")}
        selectionMode="single"
        disallowEmptySelection
        selectedKeys={[current]}
        onSelectionChange={(keys) => setActive([...keys][0] as Column)}
      >
        {columns.map((column) => (
          <ToggleButton key={column} id={column}>
            <span>{t(`column.${column}`)}</span>
            <strong>{pages[column]?.counts.columns[column] ?? 0}</strong>
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      <Check
        className="board-option"
        selected={hideEmpty}
        onChange={setHideEmpty}
      >
        {t("cases.hideEmpty")}
      </Check>
      <div className="board" aria-label={t("cases.byWork")}>
        {columns
          .filter(
            (column) =>
              !hideEmpty ||
              (pages[column]?.counts.columns[column] ?? 0) > 0 ||
              column === current,
          )
          .map((column) => {
            const page = pages[column];
            return (
              <section
                key={column}
                className="board-column"
                data-current={column === current || undefined}
                aria-labelledby={`column-${column}`}
              >
                <header>
                  <h2 id={`column-${column}`} tabIndex={-1}>
                    {t(`column.${column}`)}
                  </h2>
                  <span className="column-count">
                    {t("cases.count", {
                      count: page?.counts.columns[column] ?? 0,
                    })}
                  </span>
                </header>
                <GridList
                  className="column-cards"
                  aria-label={t("cases.columnCards", {
                    column: t(`column.${column}`),
                  })}
                  items={page?.items ?? []}
                  renderEmptyState={() => (
                    <p className="empty-column">{t("cases.emptyColumn")}</p>
                  )}
                >
                  {(item) => (
                    <GridListItem
                      id={item.id}
                      textValue={`${item.company} ${item.title}`}
                      onAction={() => onSelect(item.id)}
                    >
                      <CaseCard
                        item={item}
                        selected={selected === item.id}
                        onSelect={onSelect}
                      />
                    </GridListItem>
                  )}
                </GridList>
                {page?.next_cursor && (
                  <Button
                    className="load-more"
                    isDisabled={pending}
                    onPress={() => onMore(column)}
                  >
                    {t("cases.moreShort")}
                  </Button>
                )}
              </section>
            );
          })}
      </div>
    </>
  );
}
