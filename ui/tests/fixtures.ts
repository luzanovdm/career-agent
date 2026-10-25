import {
  columns,
  type CaseDetail,
  type CasePage,
  type Context,
  type ContactPage,
  type Receipt,
} from "../src/api/types";
/** Fictional records only. This module is never imported by production code. */
export const context: Context = {
  workspace_id: "fictional-workspace",
  revision: 1,
  profile: { display_name: "Alex Example", conversation_language: "en" },
  tracks: [
    {
      id: "track-product",
      name: "Product engineering",
      positioning: "Evidence based product work",
      selected: true,
      language: "en",
      policies: {},
    },
    {
      id: "track-platform",
      name: "Platform engineering",
      positioning: "Reliable systems",
      selected: true,
      language: "en",
      policies: {},
    },
  ],
  preferences: { theme: "system" },
  research: {
    status: "paused",
    scope: { track_ids: [], purpose: "" },
    expires_at: null,
  },
  counts: { cases: 3, contacts: 1 },
  next_missing_input: [],
};
export const caseItem: CasePage["items"][number] = {
  id: "case-aurora",
  company_id: "company-aurora",
  company: "Aurora Example",
  opportunity_id: "role-42",
  title: "Product engineer",
  kind: "vacancy",
  tracks: [
    {
      id: "track-product",
      name: "Product engineering",
      rationale: "Recorded product work",
    },
    {
      id: "track-platform",
      name: "Platform engineering",
      rationale: "Recorded platform work",
    },
  ],
  route: "person",
  contact: { id: "contact-jordan", name: "Jordan Example", qualified: true },
  column: "prepare",
  next_action: "Revise selected message with supported evidence",
  blockers: [
    { code: "REVIEW_REQUIRED", message: "The selected draft needs review." },
  ],
  selected_packet_id: "packet-aurora",
  selected_version_id: "version-1",
  allowed_actions: [
    { intent: "agent.research", label: "Find", requires_input: true },
    { intent: "agent.prepare", label: "Prepare", requires_input: true },
    { intent: "agent.review", label: "Review", requires_input: true },
    { intent: "packet.save", label: "Revise materials", requires_input: true },
    {
      intent: "activity.record",
      label: "Record actual event",
      requires_input: true,
    },
    { intent: "case.close", label: "Close case", requires_input: true },
  ],
  version: 1,
};
export const detail: CaseDetail = {
  workspace_id: context.workspace_id,
  revision: 1,
  case: caseItem,
  notes: "Private note before editing.",
  packets: [
    {
      id: "packet-aurora",
      purpose: "referral",
      person_id: "contact-jordan",
      selected_version_id: "version-1",
    },
  ],
  selection: {
    packet_id: "packet-aurora",
    version_id: "version-1",
    case_id: caseItem.id,
    person_id: "contact-jordan",
    purpose: "referral",
    slots: [
      {
        name: "message",
        artifact_id: "artifact-message",
        sha256: "a".repeat(64),
        media_type: "text/markdown",
        text: "Hello Jordan,\n\nI would value your perspective on the product engineering role at Aurora Example.\n\nAlex",
        download_url: "/api/v1/artifacts/artifact-message/download",
      },
      {
        name: "resume",
        artifact_id: "artifact-resume",
        sha256: "b".repeat(64),
        media_type: "text/markdown",
        text: "# Alex Example\n\nSynthetic career evidence for tests.",
        download_url: "/api/v1/artifacts/artifact-resume/download",
      },
      {
        name: "interview",
        artifact_id: "interview-1",
        sha256: "c".repeat(64),
        media_type: "text/markdown",
        text: JSON.stringify({
          format: "career-agent.interview/1",
          turns: [
            {
              kind: "question",
              text: "How do you connect product decisions to delivery?",
              status: "hypothesis",
              source_ids: [],
              terms: [],
            },
            {
              kind: "answer",
              text: "Use a confirmed project example. Describe your contribution and the evidence available; do not invent a metric.",
              status: "outline",
              source_ids: [],
              terms: [],
            },
          ],
        }),
        download_url: "/api/v1/artifacts/interview-1/download",
      },
    ],
    assessment: {
      saved: true,
      prepared: false,
      qualified: true,
      issues: [],
      unknowns: ["Confirm the current role scope"],
    },
    review: null,
    version: 1,
  },
  history: [
    {
      id: "activity-1",
      kind: "coverage",
      occurred_at: "2026-10-24T12:00:00Z",
      evidence: "Fictional source inspected in isolated test.",
      version_id: null,
    },
  ],
  interview: [
    {
      slot: "interview",
      kind: "question",
      status: "hypothesis",
      sources: [],
      terms: [],
      text: "How do you connect product decisions to delivery?",
      artifact_id: "interview-1",
    },
    {
      slot: "interview",
      kind: "answer",
      status: "outline",
      sources: [],
      terms: [],
      text: "Use a confirmed project example. Describe your contribution and the evidence available; do not invent a metric.",
      artifact_id: "interview-1",
    },
  ],
  sources: [
    {
      id: "source-1",
      locator: "https://aurora.example/role-42",
      excerpt: "Fictional source excerpt.",
      observed_at: "2026-10-24T12:00:00Z",
      readable: true,
    },
  ],
};
export function page(column?: string, revision = 1): CasePage {
  const other = [
    {
      ...caseItem,
      id: "case-harbor",
      company: "Harbor Example",
      title: "Platform engineer",
      column: "qualify" as const,
      contact: null,
      blockers: [],
      next_action: "Verify current affiliation",
      tracks: caseItem.tracks.slice(1),
    },
    {
      ...caseItem,
      id: "case-orbit",
      company: "Orbit Example",
      title: "Product collaboration",
      kind: "project" as const,
      column: "waiting" as const,
      blockers: [],
      next_action: "Wait for an actual response",
      tracks: caseItem.tracks.slice(0, 1),
    },
  ];
  const items = [caseItem, ...other];
  return {
    workspace_id: context.workspace_id,
    revision,
    items: column ? items.filter((item) => item.column === column) : items,
    next_cursor: null,
    counts: {
      total: 3,
      columns: Object.fromEntries(
        columns.map((key) => [
          key,
          items.filter((item) => item.column === key).length,
        ]),
      ) as CasePage["counts"]["columns"],
    },
    qualified_people: 1,
  };
}
export const contacts: ContactPage = {
  workspace_id: context.workspace_id,
  revision: 1,
  next_cursor: null,
  total: 1,
  items: [
    {
      id: "contact-jordan",
      name: "Jordan Example",
      company_id: "company-aurora",
      affiliation: "current",
      relevance: "Relevant product engineering contact",
      sources: [
        {
          source_id: "source-1",
          axes: ["identity", "affiliation", "relevance"],
          assessment: "supports",
        },
      ],
      route: {
        kind: "profile",
        value: "https://aurora.example/team/jordan",
        source_id: "source-1",
      },
      qualified: true,
      issues: [],
      version: 1,
    },
  ],
};
export const receipt: Receipt = {
  workspace_id: context.workspace_id,
  revision: 2,
  request_id: "request-fixture",
  outcome: "satisfied",
  saved_ids: ["case-aurora"],
  selected_packet_ids: [],
  issues: [],
  external_actions: { performed: 0 },
};
export function board(revision = 1) {
  const base = page(undefined, revision);
  return {
    ...base,
    columns: Object.fromEntries(
      columns.map((column) => [
        column,
        { items: page(column, revision).items, next_cursor: null },
      ]),
    ) as import("../src/api/types").BoardPage["columns"],
  };
}
export const handoff: import("../src/api/types").AgentHandoff = {
  workspace_id: context.workspace_id,
  revision: 1,
  descriptor: {
    id: "intent-fixture",
    workspace_id: context.workspace_id,
    revision: 1,
    intent: "agent.review",
    scope: {
      case_ids: ["case-aurora"],
      packet_ids: ["packet-aurora"],
      version_ids: ["version-1"],
      track_ids: ["track-product", "track-platform"],
    },
    status: "not_executed",
  },
  prompt:
    "Use installed workspace fictional-workspace. Review exact case-aurora and packet-aurora version-1. Resolve the intent before work. Do not send anything.",
  executed: false,
  external_actions: { performed: 0 },
};
