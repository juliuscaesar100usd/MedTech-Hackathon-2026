// Typed API client for MedArchive. All calls go through a tiny fetch wrapper.
// Base URL: import.meta.env.VITE_API_BASE || '/api' (dev proxied by Vite).

import type { Money } from './format';

export const API_BASE: string = import.meta.env.VITE_API_BASE || '/api';

// ---------------------------------------------------------------------------
// Types mirroring the backend contract
// ---------------------------------------------------------------------------

export interface ServiceOut {
  service_id: number | string;
  service_name: string;
  synonyms: string[];
  category: string | null;
  icd_code: string | null;
  is_active: boolean;
}

export interface PartnerOut {
  partner_id: number | string;
  name: string;
  city: string | null;
  address: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  is_active: boolean;
}

export interface PartnerPriceOut {
  partner: PartnerOut;
  item_id: number | string;
  service_name_raw: string | null;
  price_resident_kzt: Money;
  price_nonresident_kzt: Money;
  currency_original: string | null;
  effective_date: string | null;
  is_verified: boolean;
  match_confidence: number | string | null;
}

export interface ServicePriceOut {
  item_id: number | string;
  service_id: number | string | null;
  service_name: string | null;
  service_name_raw: string | null;
  category: string | null;
  price_resident_kzt: Money;
  price_nonresident_kzt: Money;
  currency_original: string | null;
  effective_date: string | null;
  match_status: string | null;
  is_verified: boolean;
}

export interface SearchServiceHit {
  type: string;
  service_id: number | string;
  service_name: string;
  category: string | null;
  partner_count: number | null;
  min_price_kzt: Money;
  max_price_kzt: Money;
  score: number | null;
}

export interface SearchPartnerHit {
  type: string;
  partner_id: number | string;
  name: string;
  city: string | null;
  service_count: number | null;
  score: number | null;
}

export interface SearchResult {
  query: string;
  services: SearchServiceHit[];
  partners: SearchPartnerHit[];
}

// --- AI assistant (chatbot) ---
export type AssistantIntent = 'find_service' | 'find_partner' | 'compare' | 'unknown';
export type ResidentPref = 'resident' | 'nonresident' | 'any';
export type SortOrder = 'cheapest' | 'expensive' | 'relevance';

export interface AssistantPreferences {
  intent: AssistantIntent;
  services: string[];
  category: string | null;
  city: string | null;
  partner: string | null;
  max_price_kzt: Money;
  min_price_kzt: Money;
  resident: ResidentPref;
  sort: SortOrder;
  limit: number;
  language: string | null;
  raw_query: string;
  notes: string[];
}

export interface AssistantOffer {
  item_id: string | number;
  partner_id: string | number;
  partner_name: string;
  city: string | null;
  price_resident_kzt: Money;
  price_nonresident_kzt: Money;
  price_shown_kzt: Money;
  currency_original: string;
  effective_date: string | null;
  is_verified: boolean;
}

export interface AssistantServiceResult {
  type: 'service';
  service_id: string | number | null;
  service_name: string;
  category: string | null;
  partner_count: number;
  best_price_kzt: Money;
  min_price_kzt: Money;
  max_price_kzt: Money;
  offers: AssistantOffer[];
  match_reason: string;
  score: number;
}

export interface AssistantPartnerResult {
  type: 'partner';
  partner_id: string | number;
  name: string;
  city: string | null;
  service_count: number;
  score: number;
}

export interface AssistantChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AssistantReply {
  reply: string;
  preferences: AssistantPreferences;
  services: AssistantServiceResult[];
  partners: AssistantPartnerResult[];
  used_llm: boolean;
  parser: 'llm' | 'rule_based';
  suggestions: string[];
}

export interface AssistantStatus {
  enabled: boolean;
  llm_available: boolean;
  model: string;
}

export interface MatchCandidate {
  service_id: number | string;
  service_name: string;
  category: string | null;
  score: number | null;
  method: string | null;
}

export interface UnmatchedItemOut {
  item_id: number | string;
  doc_id: number | string | null;
  partner_id: number | string | null;
  partner_name: string | null;
  service_name_raw: string | null;
  service_code_source: string | null;
  price_resident_kzt: Money;
  match_status: string | null;
  match_confidence: number | string | null;
  candidates: MatchCandidate[];
}

export interface PriceItemOut {
  item_id: number | string;
  service_id?: number | string | null;
  partner_id?: number | string | null;
  service_name_raw?: string | null;
  price_resident_kzt?: Money;
  price_nonresident_kzt?: Money;
  currency_original?: string | null;
  effective_date?: string | null;
  match_status?: string | null;
  match_confidence?: number | string | null;
  is_verified?: boolean;
  needs_review?: boolean;
  [key: string]: unknown;
}

/** Verification queue rows: PriceItemOut-like with extra defensive fields. */
export interface VerificationItemOut extends PriceItemOut {
  partner_name?: string | null;
  service_name?: string | null; // proposed match
  anomaly_flags?: string[];
}

export interface BatchOut {
  batch_id: number | string;
  archive_name: string | null;
  status: string | null;
  total_files: number | null;
  processed_files: number | null;
  error_files: number | null;
  created_at: string | null;
  finished_at: string | null;
}

export interface CatalogUploadResult {
  created: number;
  updated: number;
}

export interface PriceDocumentOut {
  doc_id: number | string;
  partner_id: number | string | null;
  batch_id: number | string | null;
  file_name: string | null;
  file_format: string | null;
  effective_date: string | null;
  parsed_at: string | null;
  parse_status: string | null;
  parse_log: string | null;
  language: string | null;
  n_items: number | null;
  n_matched: number | null;
}

export interface DashboardStats {
  partners: number;
  services: number;
  documents: number;
  documents_done: number;
  documents_error: number;
  documents_pending: number;
  price_items: number;
  items_matched_auto: number;
  items_matched_manual: number;
  items_needs_review: number;
  items_unmatched: number;
  items_verified: number;
  items_with_anomalies: number;
  normalization_rate: number;
  auto_normalization_rate: number;
  verification_rate: number;
  by_category: Record<string, number>;
  by_city: Record<string, number>;
  recent_batches: BatchOut[];
}

// Request bodies
export interface NewServiceInput {
  service_name: string;
  synonyms: string[];
  category: string | null;
  icd_code: string | null;
}

export interface MatchInput {
  item_id: number | string;
  service_id?: number | string;
  new_service?: NewServiceInput;
  note?: string;
  operator?: string;
}

export interface VerifyInput {
  item_id: number | string;
  approve: boolean;
  service_id?: number | string;
  price_resident_kzt?: number;
  price_nonresident_kzt?: number;
  note?: string;
  operator?: string;
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

type QueryParams = Record<string, string | number | boolean | null | undefined>;

function buildUrl(path: string, params?: QueryParams): string {
  const url = `${API_BASE}${path}`;
  if (!params) return url;
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    qs.append(key, String(value));
  }
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request<T>(
  path: string,
  opts: { method?: string; params?: QueryParams; body?: unknown; isForm?: boolean } = {},
): Promise<T> {
  const { method = 'GET', params, body, isForm } = opts;
  const url = buildUrl(path, params);

  const init: RequestInit = { method };
  if (body !== undefined) {
    if (isForm) {
      init.body = body as FormData;
    } else {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
  }

  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (err) {
    throw new ApiError(
      `Network error: could not reach the API. ${(err as Error)?.message ?? ''}`.trim(),
      0,
      null,
    );
  }

  const parsed = await parseBody(res);
  if (!res.ok) {
    const detail =
      (parsed && typeof parsed === 'object' && 'detail' in parsed
        ? String((parsed as Record<string, unknown>).detail)
        : null) ?? `Request failed (${res.status})`;
    throw new ApiError(detail, res.status, parsed);
  }
  return parsed as T;
}

// ---------------------------------------------------------------------------
// Endpoint helpers
// ---------------------------------------------------------------------------

export interface ServiceQuery {
  category?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface PartnerQuery {
  city?: string;
  is_active?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  // --- Public ---
  getServices(query: ServiceQuery = {}): Promise<ServiceOut[]> {
    return request<ServiceOut[]>('/services', { params: query as QueryParams });
  },

  getServicePartners(id: number | string): Promise<PartnerPriceOut[]> {
    return request<PartnerPriceOut[]>(`/services/${id}/partners`);
  },

  getPartners(query: PartnerQuery = {}): Promise<PartnerOut[]> {
    return request<PartnerOut[]>('/partners', { params: query as QueryParams });
  },

  getPartner(id: number | string): Promise<PartnerOut> {
    return request<PartnerOut>(`/partners/${id}`);
  },

  getPartnerServices(id: number | string): Promise<ServicePriceOut[]> {
    return request<ServicePriceOut[]>(`/partners/${id}/services`);
  },

  search(q: string): Promise<SearchResult> {
    return request<SearchResult>('/search', { params: { q } });
  },

  // --- AI assistant ---
  assistantStatus(): Promise<AssistantStatus> {
    return request<AssistantStatus>('/assistant/status');
  },

  assistantChat(message: string, history: AssistantChatMessage[] = []): Promise<AssistantReply> {
    return request<AssistantReply>('/assistant/chat', {
      method: 'POST',
      body: { message, history },
    });
  },

  // --- Operator queues ---
  getUnmatched(limit = 50, offset = 0): Promise<UnmatchedItemOut[]> {
    return request<UnmatchedItemOut[]>('/unmatched', { params: { limit, offset } });
  },

  match(input: MatchInput): Promise<PriceItemOut> {
    return request<PriceItemOut>('/match', { method: 'POST', body: input });
  },

  // --- Admin ---
  uploadArchive(file: File): Promise<BatchOut> {
    const form = new FormData();
    form.append('file', file);
    return request<BatchOut>('/admin/upload', { method: 'POST', body: form, isForm: true });
  },

  uploadCatalog(file: File): Promise<CatalogUploadResult> {
    const form = new FormData();
    form.append('file', file);
    return request<CatalogUploadResult>('/admin/catalog', {
      method: 'POST',
      body: form,
      isForm: true,
    });
  },

  getDocuments(query: { status?: string; limit?: number; offset?: number } = {}): Promise<
    PriceDocumentOut[]
  > {
    return request<PriceDocumentOut[]>('/admin/documents', { params: query as QueryParams });
  },

  getBatches(): Promise<BatchOut[]> {
    return request<BatchOut[]>('/admin/batches');
  },

  getVerification(limit = 50, offset = 0): Promise<VerificationItemOut[]> {
    return request<VerificationItemOut[]>('/admin/verification', { params: { limit, offset } });
  },

  verify(input: VerifyInput): Promise<PriceItemOut> {
    return request<PriceItemOut>('/admin/verify', { method: 'POST', body: input });
  },

  getDashboard(): Promise<DashboardStats> {
    return request<DashboardStats>('/admin/dashboard');
  },
};
