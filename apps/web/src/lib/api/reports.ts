import { apiRequest, apiRequestWithMeta } from "@/lib/api/http";
import type {
  ReportCaseListResponse,
  ReportCaseResponse,
  StaffActionResponse,
  StaffReportDetail,
  StaffReportListResponse,
} from "@/lib/api/generated/types.gen";

export async function listOwnReports(sessionToken: string): Promise<ReportCaseListResponse> {
  return apiRequest<ReportCaseListResponse>("/v1/reports", { sessionToken });
}

export async function createReportCase(
  sessionToken: string,
  body: {
    object_kind: "component" | "setup";
    stable_id: string;
    version: string;
    content_digest: string;
    diagnostics?: string;
    diagnostics_previewed?: boolean;
    vulnerability?: boolean;
    error_code?: string;
    idempotency_key: string;
  },
): Promise<{ body: ReportCaseResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<ReportCaseResponse>("/v1/reports", {
    method: "POST",
    sessionToken,
    body: {
      schema_version: 1,
      object_kind: body.object_kind,
      stable_id: body.stable_id,
      version: body.version,
      content_digest: body.content_digest,
      diagnostics: body.diagnostics ?? "",
      diagnostics_previewed: body.diagnostics_previewed ?? false,
      vulnerability: body.vulnerability ?? false,
      error_code: body.error_code ?? "",
      harness_id: "",
      harness_version: "",
      provider_version: "",
      operation_id: "",
      validation_snapshot_ids: [],
      idempotency_key: body.idempotency_key,
    },
  });
  return { body: result.data, operationId: result.operationId };
}

export async function listStaffReports(sessionToken: string): Promise<StaffReportListResponse> {
  return apiRequest<StaffReportListResponse>("/v1/staff/reports", {
    sessionToken,
    query: { schema_version: 1, page_size: 50 },
  });
}

export async function readStaffReport(
  sessionToken: string,
  caseId: string,
): Promise<StaffReportDetail> {
  return apiRequest<StaffReportDetail>(`/v1/staff/reports/${caseId}`, { sessionToken });
}

export async function staffTriageReport(
  sessionToken: string,
  caseId: string,
  state: "triaged" | "awaiting_author" | "security_escalated" | "resolved" | "dismissed",
  reason: string,
  idempotencyKey: string,
): Promise<{ body: ReportCaseResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<ReportCaseResponse>(
    `/v1/staff/reports/${caseId}/triage`,
    {
      method: "POST",
      sessionToken,
      body: {
        schema_version: 1,
        state,
        reason,
        idempotency_key: idempotencyKey,
      },
    },
  );
  return { body: result.data, operationId: result.operationId };
}

export async function staffVersionLifecycle(
  sessionToken: string,
  body: {
    object_kind: "component" | "setup";
    stable_id: string;
    version: string;
    action: "block" | "hide" | "restore";
    reason: string;
    idempotency_key: string;
  },
): Promise<{ body: StaffActionResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<StaffActionResponse>("/v1/staff/versions/lifecycle", {
    method: "POST",
    sessionToken,
    body: { schema_version: 1, ...body },
  });
  return { body: result.data, operationId: result.operationId };
}

export async function staffAuthorVerified(
  sessionToken: string,
  body: {
    subject_account_id: string;
    verified: boolean;
    reason: string;
    idempotency_key: string;
  },
): Promise<{ body: StaffActionResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<StaffActionResponse>("/v1/staff/author-verified", {
    method: "POST",
    sessionToken,
    body: { schema_version: 1, ...body },
  });
  return { body: result.data, operationId: result.operationId };
}
