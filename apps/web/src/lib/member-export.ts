/**
 * Serializes generated invitation links for download (#201).
 *
 * Inverse of `member-import`: the same six formats round-trip, so a file an
 * admin downloads can be pasted back into the bulk importer elsewhere.
 */

import type {
  CorporateContext,
  CorporateInvitation,
  CorporateMember,
} from "@/lib/api/generated/types.gen";
import { invitationDisplayState } from "@/lib/corporate-invitation-state";

export type InvitationLinkRow = {
  displayName: string;
  email: string;
  link: string;
};

export type ExportFormat = "csv" | "md" | "json" | "xml" | "html" | "txt";

export const EXPORT_FORMATS: readonly ExportFormat[] = [
  "csv",
  "md",
  "json",
  "xml",
  "html",
  "txt",
] as const;

const MIME: Record<ExportFormat, string> = {
  csv: "text/csv",
  md: "text/markdown",
  json: "application/json",
  xml: "application/xml",
  html: "text/html",
  txt: "text/plain",
};

const esc = (value: string, pattern: RegExp, wrap: (s: string) => string) =>
  pattern.test(value) ? wrap(value) : value;

const csvCell = (value: string) => {
  const safe = /^[\s]*[=+@-]/.test(value) ? `'${value}` : value;
  return esc(safe, /[",\r\n]/, (s) => `"${s.replace(/"/g, '""')}"`);
};

export function exportPeopleCsv(rows: readonly (readonly string[])[]): string {
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
}

export function downloadPeopleCsv(filename: string, rows: readonly (readonly string[])[]): void {
  const url = URL.createObjectURL(
    new Blob(["\uFEFF", exportPeopleCsv(rows)], { type: "text/csv;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

const xmlEscape = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function exportInvitationLinks(
  rows: readonly InvitationLinkRow[],
  format: ExportFormat,
): { filename: string; mime: string; content: string } {
  const filename = `invitations.${format}`;
  const mime = MIME[format];
  switch (format) {
    case "csv":
      return {
        filename,
        mime,
        content: [
          "display_name,email,link",
          ...rows.map((r) => `${csvCell(r.displayName)},${csvCell(r.email)},${csvCell(r.link)}`),
        ].join("\n"),
      };
    case "json":
      return {
        filename,
        mime,
        content: `${JSON.stringify(
          rows.map((r) => ({
            display_name: r.displayName,
            email: r.email,
            link: r.link,
          })),
          null,
          2,
        )}\n`,
      };
    case "xml":
      return {
        filename,
        mime,
        content: [
          `<?xml version="1.0" encoding="UTF-8"?>`,
          `<invitations>`,
          ...rows.map(
            (r) =>
              `  <invitation><display_name>${xmlEscape(r.displayName)}</display_name>` +
              `<email>${xmlEscape(r.email)}</email><link>${xmlEscape(r.link)}</link></invitation>`,
          ),
          `</invitations>`,
        ].join("\n"),
      };
    case "html":
      return {
        filename,
        mime,
        content: [
          `<!doctype html><html><body><table>`,
          `<thead><tr><th>Display name</th><th>Email</th><th>Link</th></tr></thead>`,
          `<tbody>`,
          ...rows.map(
            (r) =>
              `<tr><td>${xmlEscape(r.displayName)}</td><td>${xmlEscape(r.email)}</td>` +
              `<td><a href="${xmlEscape(r.link)}">invitation</a></td></tr>`,
          ),
          `</tbody></table></body></html>`,
        ].join("\n"),
      };
    case "md":
      return {
        filename,
        mime,
        content: [
          `| Display name | Email | Link |`,
          `| --- | --- | --- |`,
          ...rows.map((r) => `| ${r.displayName} | ${r.email} | ${r.link} |`),
        ].join("\n"),
      };
    case "txt":
      return {
        filename,
        mime,
        content: rows.map((r) => `${r.displayName} <${r.email}> ${r.link}`).join("\n"),
      };
  }
}

export function downloadInvitationLinks(
  rows: readonly InvitationLinkRow[],
  format: ExportFormat,
): void {
  const { filename, mime, content } = exportInvitationLinks(rows, format);
  const url = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function exportInvitationDirectory(
  rows: readonly CorporateInvitation[],
  context: CorporateContext,
  members: readonly CorporateMember[],
  stamp: number,
) {
  downloadPeopleCsv("invitations.csv", [
    ["display_name", "email", "role", "status", "teams", "invited_by", "sent", "expires"],
    ...rows.map((row) => [
      row.display_name,
      row.recipient_email,
      row.role,
      invitationDisplayState(row, stamp),
      context.teams
        .filter((team) => row.team_ids.includes(team.team_id))
        .map((team) => team.name)
        .join("; "),
      members.find((member) => member.account_id === row.issuer_account_id)?.display_name ??
        row.issuer_account_id ??
        "",
      row.created_at,
      row.expires_at,
    ]),
  ]);
}
