export type WorkflowStatus =
  | "PENDING"
  | "PROCESSING"
  | "REVIEW_REQUIRED"
  | "COMPLETED"
  | "FAILED";

export type MatchConfidence = "HIGH" | "MEDIUM" | "LOW" | "NONE";

export interface DetectedFace {
  id: string;
  box_x: number;
  box_y: number;
  box_w: number;
  box_h: number;
  detection_confidence: number;
  matched_student_id?: string | null;
  matched_student_name?: string | null;
  cosine_distance_score?: number | null;
  inference_confidence: MatchConfidence;
  is_blurred_by_system: boolean;
  is_blurred_override: boolean;
  is_final_blurred: boolean;
}

export interface MediaUploadDetail {
  id: string;
  original_filename: string;
  workflow_status: WorkflowStatus;
  raw_url?: string | null;
  processed_url?: string | null;
  error_detail?: string | null;
  created_at: string;
  updated_at: string;
  detected_faces: DetectedFace[];
}

export interface MediaUploadSummary {
  id: string;
  original_filename: string;
  workflow_status: WorkflowStatus;
  face_count: number;
  blurred_count: number;
  created_at: string;
  updated_at: string;
}

export interface Student {
  id: string;
  first_name: string;
  last_name: string;
  student_id_number: string;
  grade_level: string;
  parent_consent_signed: boolean;
  reference_image_path: string;
  created_at: string;
  updated_at: string;
}

export interface OverrideEntry {
  face_id: string;
  override_state: boolean;
}
