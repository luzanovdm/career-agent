import type { Snapshot, Track } from "../api/types";
export interface EvidenceSource {
  id: string;
  locator: string;
  excerpt: string;
  observed_at: string;
  readable: boolean;
  excerpt_truncated?: boolean;
}
export interface EvidenceClaim {
  id: string;
  assertion: string;
  meaning: string;
  confirmation: string;
  disclosure: string;
  contradicted: boolean | number;
  source_ids: string[];
  detail?: Record<string, unknown>;
}
export interface EvidenceAnswer {
  id: string;
  meaning: string;
  scope: Record<string, unknown>;
  units: Record<string, unknown>;
  disposition: string;
  value: unknown;
  evidence: string;
  response_state: "pending" | "provided";
  reusable_here: boolean;
  value_reusable_here: boolean;
  scope_unresolved: boolean;
  valid_now: boolean;
  valid_from: string | null;
  valid_until: string | null;
}
export interface EvidencePagination {
  total: number;
  offset: number;
  returned: number;
  remaining: number;
  omitted_by_scope: number;
}
export interface EvidenceContext extends Snapshot {
  tracks?: Track[];
  evidence?: {
    claims: EvidenceClaim[];
    answers: EvidenceAnswer[];
    sources: EvidenceSource[];
  };
  pagination?: Record<string, EvidencePagination>;
  next_cursor?: string | null;
  partial?: boolean;
  source?: EvidenceSource;
  claim?: EvidenceClaim;
  answer?: EvidenceAnswer;
}
