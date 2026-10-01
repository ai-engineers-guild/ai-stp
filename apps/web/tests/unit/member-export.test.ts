import { describe, expect, it } from "vitest";

import { EXPORT_FORMATS, exportInvitationLinks, exportPeopleCsv } from "@/lib/member-export";
import { parseMemberImport } from "@/lib/member-import";

const ROWS = [
  {
    displayName: 'Jane "JD" Doe',
    email: "jane@example.com",
    link: "https://app.example/en/corporate-invitations/invite_1#token=abc",
  },
  {
    displayName: "John Smith",
    email: "john@example.com",
    link: "https://app.example/en/corporate-invitations/invite_2#token=def",
  },
];

describe("exportInvitationLinks", () => {
  it("supports all six formats", () => {
    expect(EXPORT_FORMATS).toEqual(["csv", "md", "json", "xml", "html", "txt"]);
    for (const format of EXPORT_FORMATS) {
      const result = exportInvitationLinks(ROWS, format);
      expect(result.filename).toBe(`invitations.${format}`);
      expect(result.content.length).toBeGreaterThan(0);
    }
  });

  it("escapes CSV cells containing quotes and commas", () => {
    const { content, mime } = exportInvitationLinks(ROWS, "csv");
    expect(mime).toBe("text/csv");
    expect(content).toContain('"Jane ""JD"" Doe"');
    expect(content).toContain("john@example.com");
  });

  it("emits JSON objects with snake_case keys", () => {
    const { content } = exportInvitationLinks(ROWS, "json");
    const parsed = JSON.parse(content) as Array<Record<string, string>>;
    expect(parsed[0]).toEqual({
      display_name: 'Jane "JD" Doe',
      email: "jane@example.com",
      link: ROWS[0]?.link,
    });
  });

  it("escapes XML entities in markup formats", () => {
    const rows = [
      { displayName: "A & B <x>", email: "ab@example.com", link: "https://x/?a=1&b=2" },
    ];
    expect(exportInvitationLinks(rows, "xml").content).toContain("A &amp; B &lt;x&gt;");
    expect(exportInvitationLinks(rows, "html").content).toContain("a=1&amp;b=2");
  });

  it("round-trips exports through the import parser", () => {
    for (const format of ["csv", "md", "json", "xml", "txt"] as const) {
      const { filename, content } = exportInvitationLinks(ROWS, format);
      const parsed = parseMemberImport(content, filename);
      expect(parsed.map((row) => row.email)).toEqual(ROWS.map((row) => row.email));
    }
  });
});

it("keeps cells intact and neutralizes spreadsheet formulas in directory exports", () => {
  expect(
    exportPeopleCsv([
      ["name", "email"],
      ["=CMD()", 'a,"b"\nc'],
      ["  @SUM(A1)", "safe"],
    ]),
  ).toBe('name,email\r\n\'=CMD(),"a,""b""\nc"\r\n\'  @SUM(A1),safe');
});
