// In dev the Vite proxy forwards /auth, /drive, /documents, /sync to the backend.
// In production set VITE_API_URL to the backend origin.
const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }

  return res.json() as Promise<T>;
}

export interface DealDocSlot {
  id: number;
  file_id: string;
  name: string;
  date: string | null;
  description: string | null;
  vectorizer_doc_id: string | null;
}

export interface DealDocSlots {
  pitch_deck: DealDocSlot | null;
  investment_memo: DealDocSlot | null;
  prescreening_report: DealDocSlot | null;
  meeting_minutes: DealDocSlot | null;
  due_diligence_report: DealDocSlot | null;
}

export interface ArchivedDoc {
  id: number;
  file_id: string;
  type: string;
  name: string;
  date: string | null;
}

export interface LockedFileDoc {
  id: number;
  file_id: string;
  name: string;
  date: string | null;
}

export interface LockedFileWithDeal {
  id: number;
  file_id: string;
  name: string;
  date: string | null;
  deal_id: number | null;
  deal_name: string | null;
}

export interface DealFieldResponse {
  field_name: string;
  field_label: string | null;
  field_type: string | null;
  section: string | null;
  value: string | null;
  value_formatted: string | null;
}

export interface DealResponse {
  id: number;
  name: string;
  documents: DealDocSlots;
  archived: ArchivedDoc[];
  doc_count: number;
  investment_type: string | null;
  deal_status: string | null;
  deal_reason: string | null;
  deal_fields: DealFieldResponse[];
  locked_files: LockedFileDoc[];
}

export interface DriveFolder {
  id: string;
  label: string;
}

export interface OrgBrief {
  id: number;
  name: string;
}

export type UserPayload = {
  id: number;
  email: string;
  folder_id: string | null;
  folder_ids: DriveFolder[] | null;
  company_name: string | null;
  custom_prompt: string | null;
  organization_id: number | null;
  organization: OrgBrief | null;
  needs_org: boolean;
};

export interface OrgResponse {
  id: number;
  name: string;
  custom_prompt: string | null;
  classification_limit: number;
  vectorization_limit: number;
  created_at: string;
}

export interface OrgQuotaResponse {
  id: number;
  name: string;
  classification_used: number;
  classification_limit: number;
  vectorization_used: number;
  vectorization_limit: number;
  member_count: number;
  processing_timeout_hours: number;
}

export interface OrgListItem {
  id: number;
  name: string;
  member_count: number;
}

// ── Merge preview types ───────────────────────────────────────────────────

export interface MergeDocInfo {
  id: number;
  file_name: string;
  date: string | null;
  description: string | null;
}

export interface MergeDealInfo {
  id: number;
  name: string;
  doc_count: number;
}

export interface MergeConflict {
  doc_type: string;
  doc_type_label: string;
  source_doc: MergeDocInfo;
  target_doc: MergeDocInfo;
  recommendation: string; // "keep_source" | "keep_target"
  reason: string;
}

export interface MergePreviewResponse {
  source_deal: MergeDealInfo;
  target_deal: MergeDealInfo;
  conflicts: MergeConflict[];
  documents_to_move: number;
}

export interface MergeResolution {
  doc_type: string;
  keep_doc_id: number;
}

// ── Worker run types ─────────────────────────────────────────────────────

export interface WorkerProgress {
  run_id: number;
  stage: string | null;
  status: string; // pending | running | completed | failed | cancelled
  data: Record<string, number>;
}

export interface WorkerRunHistory {
  id: number;
  status: string;
  current_stage: string | null;
  progress_data: Record<string, number> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export const api = {
  /** Redirect browser to Google OAuth */
  loginWithGoogle(): void {
    window.location.href = `${BASE_URL}/auth/login`;
  },

  getMe(): Promise<UserPayload> {
    return apiFetch("/auth/me");
  },

  updateProfile(data: { company_name?: string; custom_prompt?: string | null }): Promise<UserPayload> {
    return apiFetch("/auth/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  addFolder(folderPath: string): Promise<{ folder_id: string; label: string; folders: DriveFolder[] }> {
    return apiFetch("/drive/folder", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath }),
    });
  },

  removeFolder(folderId: string): Promise<{ folders: DriveFolder[] }> {
    return apiFetch(`/drive/folder/${folderId}`, { method: "DELETE" });
  },

  getSyncStatus(): Promise<{
    status: string;
    next_sync: string;
    drive_connected: boolean;
    folder_configured: boolean;
    total_documents: number;
    processed_documents: number;
    pending_documents: number;
    is_running: boolean;
    active_run_id: number | null;
  }> {
    return apiFetch("/sync/status");
  },

  startPipelineRun(): Promise<{ run_id: number; status: string }> {
    return apiFetch("/sync/run", { method: "POST" });
  },

  cancelPipelineRun(): Promise<{ cancelled: boolean }> {
    return apiFetch("/sync/run/cancel", { method: "POST" });
  },

  getRunHistory(limit = 20): Promise<WorkerRunHistory[]> {
    return apiFetch(`/sync/run/history?limit=${limit}`);
  },

  getLatestDocuments(): Promise<
    { type: string; name: string; date: string | null; description: string | null }[]
  > {
    return apiFetch("/documents/latest");
  },

  getAllDocuments(): Promise<
    { id: number; file_id: string; type: string; name: string; date: string | null; description: string | null; status: string; deal_id: number | null; deal_name: string | null; version_status: string }[]
  > {
    return apiFetch("/documents/all");
  },

  getDeals(): Promise<DealResponse[]> {
    return apiFetch("/documents/deals");
  },

  getDeal(dealId: number): Promise<DealResponse> {
    return apiFetch(`/documents/deals/${dealId}`);
  },

  getLockedFiles(): Promise<LockedFileWithDeal[]> {
    return apiFetch("/documents/locked");
  },

  updateDealField(dealId: number, fieldName: string, value: string | null): Promise<DealFieldResponse> {
    return apiFetch(`/documents/deals/${dealId}/fields/${fieldName}`, {
      method: "PATCH",
      body: JSON.stringify({ value }),
    });
  },

  deleteDeal(dealId: number): Promise<{ deal_id: number; deal_name: string; documents_unlinked: number }> {
    return apiFetch(`/documents/deals/${dealId}`, { method: "DELETE" });
  },

  replaceSlotDocument(dealId: number, slotType: string, replacementDocId: number): Promise<DealResponse> {
    return apiFetch(`/documents/deals/${dealId}/slots/${slotType}`, {
      method: "PATCH",
      body: JSON.stringify({ replacement_doc_id: replacementDocId }),
    });
  },

  previewMerge(sourceDealId: number, targetDealId: number, newName?: string): Promise<MergePreviewResponse> {
    return apiFetch("/documents/deals/merge/preview", {
      method: "POST",
      body: JSON.stringify({
        source_deal_id: sourceDealId,
        target_deal_id: targetDealId,
        ...(newName ? { new_name: newName } : {}),
      }),
    });
  },

  mergeDeals(sourceDealId: number, targetDealId: number, newName?: string, resolutions?: MergeResolution[]): Promise<{
    target_deal_id: number;
    target_deal_name: string;
    source_deal_id: number;
    documents_moved: number;
    documents_superseded: number;
  }> {
    return apiFetch("/documents/deals/merge", {
      method: "POST",
      body: JSON.stringify({
        source_deal_id: sourceDealId,
        target_deal_id: targetDealId,
        ...(newName ? { new_name: newName } : {}),
        ...(resolutions?.length ? { resolutions } : {}),
      }),
    });
  },

  getDocumentStats(): Promise<{
    total_validated: number;
    shortlisted: number;
    archived: number;
    knowledge_base: number;
  }> {
    return apiFetch("/documents/stats");
  },

  // ── Organization endpoints ──────────────────────────────────────────────

  createOrg(name: string): Promise<OrgResponse> {
    return apiFetch("/org/create", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },

  joinOrg(orgId: number, migrateData: boolean): Promise<{ message: string }> {
    return apiFetch("/org/join", {
      method: "POST",
      body: JSON.stringify({ org_id: orgId, migrate_data: migrateData }),
    });
  },

  listOrgs(): Promise<OrgListItem[]> {
    return apiFetch("/org/list");
  },

  getOrgQuota(): Promise<OrgQuotaResponse> {
    return apiFetch("/org/me");
  },

  updateOrgSettings(data: {
    custom_prompt?: string | null;
    classification_limit?: number;
    vectorization_limit?: number;
  }): Promise<OrgQuotaResponse> {
    return apiFetch("/org/settings", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },
};
