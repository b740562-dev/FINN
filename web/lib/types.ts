export type Holding = {
  symbol: string;
  name: string;
  sector: string | null;
  quantity: number;
  close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  value: number;
  day_pnl: number;
  weight: number;
  documents?: number;     // reports FINN has read for this company
};

export type Profile = {
  full_name: string | null;
  gender: "female" | "male" | "non_binary" | "prefer_not_to_say" | null;
  work_company: string | null;
  work_role: string | null;
  education: string | null;
  city: string | null;
  experience: "new" | "intermediate" | "experienced" | "professional" | null;
  bio: string | null;
  email: string | null;
  is_anonymous: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type Rules = {
  volume_multiple: number;
  move_pct: number;
  categories: string[];
  overrides: Record<string, { move_pct?: number; volume_multiple?: number }>;
  all_categories?: string[];
};

export type Me = {
  user: { id: string; is_anonymous: boolean; email: string | null; is_admin?: boolean };
  holdings: Holding[];
  totals: { value: number; day_pnl: number; day_pct: number | null; as_of: string | null };
  rules: Rules;
};

export type Metric = {
  name: string;
  key: string;
  kind: "amount" | "ratio";
  value: number | null;
  prev_q: number | null;
  year_ago: number | null;
  qoq_pct?: number | null;
  yoy_pct?: number | null;
  qoq_bp?: number | null;
  yoy_bp?: number | null;
};

export type ResultsCard = {
  status: "ready" | "pending" | "unavailable";
  quarter?: string;
  quarter_label?: string;
  basis?: string;
  lender?: boolean;
  metrics?: Metric[];
  ratios?: Metric[];
  headline?: string;
  source?: string;
  flags?: string[];
  cross_check?: { metric: string; filing_text: string; stated_pct: number; card_yoy_pct: number; consistent: boolean }[];
  expected_quarter?: string;
};

export type Bio = {
  name: string;
  role: string;
  status: "ready" | "thin" | "unconfirmed" | "not_found";
  headline?: string;
  summary?: string;
  prior_roles?: { org: string; role: string }[];
  education?: string[];
  sources?: { title: string; url: string }[];
};

export type Person = { name: string; role: string; change: string; seniority: string };

export type DigestEvent = {
  symbol: string;
  company: string;
  category: string;
  label: string;
  filed_at: string;
  materiality: number;
  headline: string;
  one_liner: string | null;
  url: string | null;
  factors: string[];
  enrichment: {
    results_card?: ResultsCard;
    bios?: Bio[];
    people?: Person[];
    amount_cr?: number | null;
    rating_action?: string | null;
  };
  filing_ids: number[];
  related: number;
  score: number;
  why: string;
  weight: number;
};

export type Digest = {
  window: string;
  days: number;
  counts: { filings: number; events: number; matters: number; routine_filings: number };
  routine_mix: Record<string, number>;
  matters: DigestEvent[];
  routine: DigestEvent[];
};

export type Alert = {
  id: number;
  kind: "move" | "volume" | "filing";
  symbol: string;
  name: string;
  filing_id: number | null;
  event_date: string | null;
  created_at: string;
  read: boolean;
  payload: {
    close?: number;
    prev_close?: number;
    change_pct?: number;
    volume_ratio?: number;
    avg_volume?: number;
    volume?: number;
    triggers?: string[];
    impact_inr?: number | null;
    rule?: { move_pct: number; volume_multiple: number };
    category?: string;
    materiality?: number;
    headline?: string;
    url?: string;
  };
};

// ---- research (pull) -------------------------------------------------------
export type Citation = { id: string; doc_id?: number | null; doc_label: string; page: number | null; quote: string };

export type Section<T = Record<string, unknown>> = {
  section: string;
  status: "ready" | "needs_docs" | "error";
  model: string | null;
  generated_at: string;
  content: T;
  citations: Citation[];
  error?: string;
};

export type Overview = {
  symbol: string;
  name: string;
  sector: string | null;
  market_cap_cr: number | null;
  docs: {
    transcripts: number;
    annual_reports: number;
    items?: { id: number; kind: string; label: string; period: string | null; pages: number | null; pages_kept?: number | null; chunks?: number }[];
  };
  sections_available?: Record<string, boolean>;
};
