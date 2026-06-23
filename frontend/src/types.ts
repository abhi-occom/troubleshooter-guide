export type DocumentStatus =
  | "processing"
  | "indexed"
  | "requires_ocr"
  | "failed";

export interface DocumentRecord {
  id: string;
  filename: string;
  sha256: string;
  version: number;
  status: DocumentStatus;
  page_count: number;
  chunk_count: number;
  error: string | null;
  enrichment_status: string;
  enrichment_error: string | null;
  profile_status: string;
  faq_count: number;
  evaluation_pass_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentPage {
  items: DocumentRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface RouterProfile {
  document_id: string;
  router_name: string | null;
  model: string | null;
  product_id: string | null;
  supported_configuration: string | null;
  features: string[];
  topics: string[];
  identifier_aliases: string[];
  provenance: Record<
    string,
    { chunk_id: string; page: number; excerpt: string }
  >;
  extracted_values: Record<string, unknown>;
  manual_fields: string[];
  status: string;
  created_at: string;
  updated_at: string;
}

export interface GeneratedFaq {
  id: string;
  document_id: string;
  question: string;
  expected_topic: string | null;
  source_chunk_id: string;
  source_page: number;
  source_excerpt: string;
  approved: boolean;
  alias_active: boolean;
  passed: boolean | null;
  best_distance: number | null;
  retrieved_pages: number[];
  expected_source_found: boolean | null;
  evaluated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EnrichmentJob {
  id: string;
  document_id: string;
  status: string;
  progress: number;
  attempts: number;
  max_attempts: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface DocumentKnowledge {
  document: DocumentRecord;
  profile: RouterProfile | null;
  faqs: GeneratedFaq[];
  job: EnrichmentJob | null;
}

export interface Citation {
  document_id: string;
  document: string;
  page: number;
  excerpt: string;
  distance: number;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  rewritten_query?: string | null;
  grounded?: boolean | null;
  citations: Citation[];
  created_at: string;
}

export interface Session {
  id: string;
  created_at: string;
  last_active_at: string;
  expires_at: string;
}

export interface AskResult {
  request_id: string;
  session_id: string;
  answer: string;
  grounded: boolean;
  retrieval_status: "grounded" | "not_found";
  rewritten_query?: string | null;
  citations: Citation[];
}

export interface EvaluationDataset {
  id: string;
  name: string;
  description: string | null;
  question_count?: number;
  questions?: EvaluationQuestion[];
}

export interface EvaluationQuestion {
  id: string;
  dataset_id: string;
  question: string;
  supported: boolean;
  expected_document_id: string | null;
  expected_page_start: number | null;
  expected_page_end: number | null;
  topic: string | null;
  reference_answer: string | null;
  key_points: string[];
  notes: string | null;
  enabled: boolean;
}

export interface EvaluationRun {
  id: string;
  dataset_id: string;
  status: string;
  progress: number;
  total_questions: number;
  completed_questions: number;
  config: Record<string, unknown>;
  document_versions: Record<string, number>;
  metrics: Record<string, number | null>;
  passed: boolean | null;
  error: string | null;
}
