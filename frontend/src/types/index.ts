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

export interface DocumentItem {
  id: string;
  document_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  document_type: 'Invoice' | 'Contract' | 'Identity' | 'Application' | 'Form' | 'Other';
  classification_confidence: number;
  status: 'Verified' | 'Flagged' | 'Pending';
  raw_text: string;
  redacted_text: string;
  entities: EntityItem[];
  pii_entities: PIIEntityItem[];
  structured_data: Record<string, any>;
  confidence: number;
  pipeline_steps: PipelineStep[];
  created_at: string;
  updated_at: string;
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
  extraction_accuracy: number;
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
