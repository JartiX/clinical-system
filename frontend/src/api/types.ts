// Типы ответов API бэкенда

export interface ReviewNote {
  code: string;
  text: string;
}

export interface Patient {
  code: string;
  data_class: string;
  aliases: string[];
  documents: number;
  needs_review: number;
}

export interface DocumentSummary {
  id: string;
  title: string;
  doc_type: string;
  doc_type_label: string;
  specialty: string | null;
  specialty_label: string | null;
  doc_date: string | null;
  doc_date_precision: string;
  date_source: string;
  needs_review: boolean;
  review_notes: ReviewNote[];
  version: number;
  is_current: boolean;
  data_class: string;
  file_name: string;
  source_file_id: string;
  source_file_status: "active" | "retracted";
  fragments: number;
}

export interface Fragment {
  id: string;
  ordinal: number;
  kind: string;
  start: number;
  end: number;
  attributes: Record<string, unknown>;
}

export interface DocumentVersion {
  id: string;
  version: number;
  created_at: string;
  is_current: boolean;
}

export interface DocumentDetail extends Omit<DocumentSummary, "fragments"> {
  text: string;
  source_start: number;
  source_end: number;
  fragments: Fragment[];
  versions: DocumentVersion[];
}

export interface DocumentPatch {
  doc_date?: string | null;
  doc_type?: string;
  specialty?: string | null;
}

export interface MeasurementItem {
  no: number;
  text: string;
  answer: string | null;
  score: number | null;
}

export interface Measurement {
  id: string;
  code: string;
  date: string | null;
  epistemic_status: string;
  confirmation_status: string;
  value: {
    instrument: string;
    instrument_name: string;
    total: number | null;
    complete: boolean;
    issues: string[];
    items: MeasurementItem[];
  };
  sources: { fragment_id: string; document_id: string }[];
}

export interface VocabularyEntry {
  kind: string;
  code: string;
  label: string;
  description: string | null;
}

export interface ReportDocument {
  id: string;
  title: string;
  doc_type: string;
  date: string | null;
  action: "created" | "new_version" | "unchanged";
  version: number;
  fragments: number;
  measurements: number;
  notes: ReviewNote[];
}

export interface ReportFile {
  file: string;
  status: "processed" | "unchanged" | "skipped";
  issues: string[];
  unmapped_columns?: string[];
  skipped_rows?: string[];
  retired?: string[];
  renamed_from?: string;
  documents: ReportDocument[];
}

export interface IngestReport {
  patient: string;
  totals: {
    files: number;
    files_unchanged: number;
    files_skipped: number;
    documents_created: number;
    documents_new_version: number;
    documents_unchanged: number;
    measurements: number;
    needs_review: number;
  };
  files: ReportFile[];
}

export interface UploadResult {
  run_id: string;
  report: IngestReport;
}

export interface NameConflict {
  file: string;
  existing_received_at: string;
}

export interface SourceFileRow {
  id: string;
  file_name: string;
  media_type: string;
  size: number;
  received_at: string;
  status: "active" | "retracted";
  status_reason: string | null;
  status_changed_at: string | null;
  documents: number;
  documents_current: number;
  facts_current: number;
}

export type ActivityKind = "ingest" | "manual_edit" | "retract" | "restore" | "delete";

export interface Activity {
  id: string;
  kind: ActivityKind;
  agent: string;
  status: string;
  started_at: string;
  totals: Partial<IngestReport["totals"]>;
  title: string | null;
  changes: Record<string, [string | null, string | null]> | null;
  file: string | null;
  reason: string | null;
  affected_documents: number | null;
}

export interface ShaclResult {
  triples: number;
  conforms: boolean;
  violations: { focus: string; path: string; message: string }[];
}
