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
    topic?: string;
    locale?: "ru" | "en";
    object_kind?: "component" | "setup";
    stable_id?: string;
    version?: string;
    content_digest?: string;
    diagnostics?: string;
    diagnostics_previewed?: boolean;
    vulnerability?: boolean;
    error_code?: string;
    subject?: string;
    message?: string;
    evidence?: string;
    author_account_id?: string;
    recipient_account_id?: string;
    service?: {
      name: string;
      primary_url: string;
      description_ru: string;
      description_en: string;
      source_url: string;
      country_codes: string[];
    };
    country?: { code: string; name_ru: string; name_en: string };
    idempotency_key: string;
  },
): Promise<{ body: ReportCaseResponse; operationId: string | null }> {
  const topic = body.topic ?? "object_report";
  const objectFields =
    topic === "object_report"
      ? {
          object_kind: body.object_kind,
          stable_id: body.stable_id,
          version: body.version,
          content_digest: body.content_digest,
        }
      : topic === "component_complaint" || topic === "ownership_transfer"
        ? { object_kind: "component" as const, stable_id: body.stable_id }
        : {};
  const result = await apiRequestWithMeta<ReportCaseResponse>("/v1/requests", {
    method: "POST",
    sessionToken,
    body: {
      schema_version: 1,
      topic,
      locale: body.locale ?? "en",
      ...objectFields,
      ...(topic === "service_request" && body.service ? { service: body.service } : {}),
      ...(topic === "country_request" && body.country ? { country: body.country } : {}),
      diagnostics: body.diagnostics ?? "",
      diagnostics_previewed: body.diagnostics_previewed ?? false,
      vulnerability: body.vulnerability ?? false,
      error_code: body.error_code ?? "",
      subject: body.subject ?? "",
      message: body.message ?? "",
      evidence: body.evidence ?? "",
      author_account_id: body.author_account_id,
      recipient_account_id: body.recipient_account_id,
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

export async function createCatalogRequest(
  sessionToken: string,
  body:
    | {
        topic: "service_request";
        service: {
          name: string;
          primary_url: string;
          description_ru: string;
          description_en: string;
          source_url: string;
          country_codes: string[];
        };
      }
    | {
        topic: "country_request";
        country: { code: string; name_ru: string; name_en: string };
      },
): Promise<ReportCaseResponse> {
  return apiRequest<ReportCaseResponse>("/v1/requests", {
    method: "POST",
    sessionToken,
    body: {
      schema_version: 1,
      ...body,
      harness_id: "",
      harness_version: "",
      provider_version: "",
      operation_id: "",
      error_code: "",
      validation_snapshot_ids: [],
      diagnostics: "",
      diagnostics_previewed: false,
      vulnerability: false,
      idempotency_key: crypto.randomUUID(),
    },
  });
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
