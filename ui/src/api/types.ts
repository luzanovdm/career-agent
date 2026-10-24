/** Checked against docs/api/1.0.0.md; business state is always a server projection. */
export type Theme = "system" | "light" | "dark";
export interface Issue {
  code: string;
  message: string;
  record_id?: string;
}
export interface Snapshot {
  workspace_id: string;
  revision: number;
}
export const columns = [
  "qualify",
  "prepare",
  "ready",
  "waiting",
  "response",
  "closed",
] as const;
export type Column = (typeof columns)[number];
export const columnLabels: Record<Column, string> = {
  qualify: "Qualify",
  prepare: "Prepare / revise",
  ready: "Ready for review",
  waiting: "Waiting after transmission",
  response: "Response / next step",
  closed: "Closed",
};
export interface Track {
  id: string;
  name: string;
  positioning: string;
  selected: boolean;
  language: string;
  policies: Record<string, unknown>;
}
export interface Context extends Snapshot {
  profile: { display_name: string; conversation_language: string };
  tracks: Track[];
  preferences: { theme: Theme; ui_locale?: string };
  research: {
    status: string;
    scope: { track_ids: string[]; purpose: string };
    expires_at: string | null;
  };
  counts: { cases: number; contacts: number };
  next_missing_input: unknown[];
}
export interface Action {
  intent: string;
  label: string;
  requires_input: boolean;
}
export interface CaseSummary {
  id: string;
  company_id: string;
  company: string;
  opportunity_id: string | null;
  title: string;
  kind: "vacancy" | "project" | "speculative";
  tracks: { id: string; name: string; rationale: string }[];
  route: "person" | "form" | "unknown";
  contact: {
    id: string;
    name: string;
    qualified: boolean;
    relevance?: string;
    affiliation?: string;
    route?: { kind: string; value: string; source_id: string } | null;
  } | null;
  column: Column;
  next_action: string;
  blockers: Issue[];
  selected_packet_id: string | null;
  selected_version_id: string | null;
  allowed_actions: Action[];
  version: number;
}
export interface CasePage extends Snapshot {
  items: CaseSummary[];
  next_cursor: string | null;
  counts: { total: number; columns: Record<Column, number> };
  qualified_people: number;
}
export interface BoardPage extends Snapshot {
  columns: Record<Column, { items: CaseSummary[]; next_cursor: string | null }>;
  counts: CasePage["counts"];
  qualified_people: number;
}
export interface ContactSource {
  source_id: string;
  axes: ("identity" | "affiliation" | "relevance")[];
  assessment: "supports" | "conflicts" | "unknown";
}
export interface Contact {
  company?: string;
  id: string;
  name: string;
  company_id: string;
  affiliation: "current" | "unknown" | "conflicting" | "former";
  relevance: string;
  sources: ContactSource[];
  route: {
    kind: "profile" | "email" | "form" | "website";
    value: string;
    source_id: string;
  } | null;
  relationship?: string;
  valid_until?: string | null;
  qualified: boolean;
  issues: Issue[];
  version: number;
}
export interface ContactPage extends Snapshot {
  items: Contact[];
  next_cursor: string | null;
  total: number;
}
export interface Slot {
  name: string;
  artifact_id: string;
  sha256: string;
  media_type: string;
  text: string | null;
  download_url: string;
}
export interface Selection {
  used_claim_ids?: string[];
  answer_ids?: string[];
  packet_id: string;
  version_id: string;
  case_id: string;
  person_id: string | null;
  purpose: string;
  slots: Slot[];
  assessment: {
    saved: true;
    prepared: boolean;
    qualified: boolean;
    issues: Issue[];
    unknowns: string[];
  };
  review: { id: string; findings: unknown; limitations: unknown } | null;
  version: number;
}
export interface CaseDetail extends Snapshot {
  case: CaseSummary;
  notes: string;
  packets: {
    id: string;
    purpose: string;
    person_id: string | null;
    selected_version_id: string | null;
  }[];
  selection: Selection | null;
  history: {
    id: string;
    kind: string;
    occurred_at: string;
    evidence: string;
    version_id: string | null;
  }[];
  interview: { slot: string; text: string; artifact_id: string }[];
  sources: {
    id: string;
    locator: string;
    excerpt: string;
    observed_at: string;
    readable: boolean;
  }[];
}
export interface Receipt extends Snapshot {
  request_id: string;
  outcome: "satisfied" | "partial";
  saved_ids: string[];
  selected_packet_ids: string[];
  issues: Issue[];
  external_actions: { performed: 0 };
}
export interface CommandInputs {
  "contact.capture": Pick<
    Contact,
    | "id"
    | "name"
    | "company_id"
    | "affiliation"
    | "relevance"
    | "sources"
    | "route"
    | "relationship"
    | "valid_until"
  >;
  "preferences.set": { theme?: Theme; ui_locale?: string };
  "profile.update": { display_name: string; conversation_language: string };
  "track.save": Omit<Track, "id"> & { id?: string };
  "case.note": { case_id: string; text: string };
  "case.close": { case_id: string; reason: string; evidence: string };
  "case.reopen": { case_id: string; reason: string };
  "packet.save": {
    packet_id: string;
    documents: { slot: string; text: string }[];
    used_claim_ids: string[];
    answer_ids?: string[];
    source_version_id?: string;
  };
  "packet.select": { packet_id: string; version_id: string };
  "activity.record": {
    case_id: string;
    kind: ActivityKind;
    occurred_at: string;
    evidence: string;
    packet_id?: string;
    version_id?: string;
    resolves_activity_id?: string;
  };
  "research.control": {
    status: "active" | "paused" | "revoked";
    scope: { track_ids: string[]; purpose: string };
    evidence: string;
    expires_at?: string | null;
  };
}
export type ActivityKind =
  | "sent"
  | "uncertain"
  | "not_sent"
  | "receipt"
  | "human_reply"
  | "interview"
  | "offer"
  | "rejection"
  | "bounce"
  | "withdrawal"
  | "referral_agreed"
  | "referral_performed"
  | "coverage";
export interface Change {
  cursor: number;
  revision: number;
  kinds: string[];
  ids: string[];
  projection_keys: string[];
}
export interface Changes extends Snapshot {
  changes: Change[];
  resync_required: boolean;
}
export type AgentIntent = "agent.research" | "agent.prepare" | "agent.review";
export interface AgentHandoff extends Snapshot {
  descriptor: {
    id: string;
    workspace_id: string;
    revision: number;
    intent: AgentIntent;
    scope: {
      case_ids: string[];
      packet_ids: string[];
      version_ids: string[];
      track_ids: string[];
    };
    status: "not_executed";
  };
  prompt: string;
  executed: false;
  external_actions: { performed: 0 };
}
