export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface EntityItem {
  text: string;
  type: string; // PERSON, ORGANIZATION, LOCATION, DATE, etc.
  confidence: number;
  start?: number;
  end?: number;
  // Phase 3 — additive provenance/handling fields.
  label?: string | null;
  source?: string | null; // roberta | rule
  confidence_source?: string | null; // model | heuristic
  calibrated?: boolean | null;
  normalized_value?: string | null;
}

export interface PIIEntityItem {
  type: string; // AADHAAR, PAN, EMAIL, PHONE, BANK_ACCOUNT, CREDIT_CARD, etc.
  value: string;
  masked_value: string;
  confidence: number;
  source: string; // roberta | regex | rule
  sensitive: boolean;
  valid: boolean;
  start?: number;
  end?: number;
}

export interface PipelineStep {
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'warning' | 'failed';
  duration_ms: number;
  details?: string;
}

// Phase 3 — additive processing metadata types.
export interface QualityAssessment {
  score: number;
  level: 'excellent' | 'good' | 'fair' | 'poor';
  issues: string[];
  factors?: Record<string, any>;
}

export interface FieldValidation {
  fields: Record<string, 'valid' | 'invalid' | 'uncertain'>;
  cross_field_warnings: Array<{ field: string; code: string; message: string }>;
  failures: number;
}

export interface StageMetadata {
  current_stage?: string | null;
  stages: Array<{
    stage: string;
    status: string;
    duration_ms: number;
    error?: string | null;
  }>;
}

export interface StructuredField {
  value: any;
  confidence: number | null;
  source: 'rule' | 'ner' | 'pii' | 'derived' | 'default' | 'not_found';
  validated?: 'valid' | 'invalid' | 'uncertain';
}

export interface DocumentItem {
  id: string;
  document_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  document_type: 'Invoice' | 'Contract' | 'Identity' | 'Application' | 'Form' | 'Other';
  classification_confidence: number;
  status: 'Verified' | 'Flagged' | 'Pending';
  // Asynchronous processing lifecycle (Phase 2)
  processing_status: ProcessingStatus;
  processing_error?: { code: string; message: string } | null;
  retry_count?: number;
  raw_text: string;
  redacted_text: string;
  entities: EntityItem[];
  pii_entities: PIIEntityItem[];
  structured_data: Record<string, any>;
  // Per-field provenance/confidence metadata (value, confidence, source, validated).
  structured_fields?: Record<string, StructuredField>;
  confidence: number;
  pipeline_steps: PipelineStep[];
  // Phase 3 — additive, safe processing metadata.
  normalized_text?: string;
  structure?: Record<string, any>;
  quality?: QualityAssessment | null;
  validation?: FieldValidation | null;
  processing_metrics?: Record<string, number>;
  stage_metadata?: StageMetadata | null;
  processing_warnings?: string[];
  pipeline_version?: string | null;
  created_at: string;
  updated_at: string;
}

export type ProcessingStatus = 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';

export interface DocumentUploadResult {
  document_id: string;
  job_id: string;
  status: string;
}

export interface DocumentStatusResult {
  document_id: string;
  status: ProcessingStatus;
  validation_status?: string | null;
  progress?: number | null;
  attempts: number;
  error?: { code: string; message: string } | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RecentDocumentItem {
  document_id: string;
  filename: string;
  document_type: string;
  extracted_vendor_or_name: string;
  created_at: string;
  status: string;
  confidence: number;
}

export interface DashboardStats {
  total_processed: number;
  // Mean extraction confidence (0-100). A confidence aggregate, not accuracy.
  average_extraction_confidence: number;
  protected_entities: number;
  time_saved: string;
  type_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  recent_documents: RecentDocumentItem[];
}

export interface SecurityRule {
  rule_id: string;
  name: string;
  entity_type: string;
  enabled: boolean;
  description: string;
  mask_pattern: string;
  created_at?: string;
  updated_at?: string;
}

export interface SourceReference {
  document_id: string;
  filename: string;
  document_type: string;
  snippet: string;
  score: number;
}

export interface ChatResponse {
  answer: string;
  sources: SourceReference[];
  confidence: number;
  matched: boolean;
}
