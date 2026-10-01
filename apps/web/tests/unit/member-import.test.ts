import { describe, expect, it } from "vitest";

import { inspectMemberImport, inspectMemberCells, parseMemberImport } from "@/lib/member-import";

describe("parseMemberImport", () => {
  it("parses CSV/TSV lines into name and email pairs", () => {
    const rows = parseMemberImport(
      "email,name\njane@example.com,Jane Doe\njohn@example.com\tJohn Smith",
      "members.csv",
    );
    expect(rows).toEqual([
      { displayName: "Jane Doe", email: "jane@example.com" },
      { displayName: "John Smith", email: "john@example.com" },
    ]);
  });

  it("parses JSON arrays of objects and bare email strings", () => {
    const rows = parseMemberImport(
      JSON.stringify([
        { email: "a@example.com", display_name: "A User" },
        { email: "b@example.com", name: "B User" },
        "c@example.com",
        { unexpected: true },
      ]),
      "members.json",
    );
    expect(rows).toEqual([
      { displayName: "A User", email: "a@example.com" },
      { displayName: "B User", email: "b@example.com" },
      { displayName: "c@example.com", email: "c@example.com" },
    ]);
  });

  it("parses Markdown tables and lists", () => {
    const rows = parseMemberImport(
      "| Name | Email |\n| --- | --- |\n| Jane | jane@example.com |\n- john@example.com John",
      "members.md",
    );
    expect(rows).toEqual([
      { displayName: "Jane", email: "jane@example.com" },
      { displayName: "John", email: "john@example.com" },
    ]);
  });

  it("parses XML and HTML markup", () => {
    const rows = parseMemberImport(
      "<users><user><name>Jane</name><email>jane@example.com</email></user></users>",
      "members.xml",
    );
    expect(rows.map((row) => row.email)).toEqual(["jane@example.com"]);
    const html = parseMemberImport(
      "<tr><td>John Smith</td><td>john@example.com</td></tr>",
      "members.html",
    );
    expect(html).toEqual([{ displayName: "John Smith", email: "john@example.com" }]);
  });

  it("parses plain text lines", () => {
    const rows = parseMemberImport("Jane Doe <jane@example.com>\njohn@example.com", "members.txt");
    expect(rows).toEqual([
      { displayName: "Jane Doe", email: "jane@example.com" },
      { displayName: "john@example.com", email: "john@example.com" },
    ]);
  });

  it("normalizes case, dedupes, and skips malformed rows", () => {
    const rows = parseMemberImport(
      "jane@EXAMPLE.com, Jane\nJANE@example.com, Dupe\nnot-an-email\njohn@example.com",
      "members.csv",
    );
    expect(rows.map((row) => row.email)).toEqual(["jane@example.com", "john@example.com"]);
  });
});

it("projects headed CSV columns and handles quoted commas without applying file roles", () => {
  expect(
    inspectMemberImport('email,role,display_name\nalex@example.com,lead,"Morgan, Alex"'),
  ).toEqual([
    { email: "alex@example.com", displayName: "Morgan, Alex", rowNumber: 2, error: null },
  ]);
});
it("retains invalid, duplicate and oversized names for review", () => {
  const rows = inspectMemberImport(
    `email,display_name\na@example.com,A\nA@example.com,Duplicate\nbad,Bad\nb@example.com,${"B".repeat(81)}`,
  );
  expect(rows.map((row) => row.error)).toEqual([
    null,
    "duplicateEmail",
    "invalidEmail",
    "nameTooLong",
  ]);
});
it("shares spreadsheet projection and bounds the row count", () => {
  expect(
    inspectMemberCells([
      ["display_name", "email"],
      ["Alex", "Alex@Example.com"],
    ])[0],
  ).toMatchObject({ email: "alex@example.com", displayName: "Alex", error: null });
  expect(() =>
    inspectMemberImport(
      Array.from({ length: 501 }, (_, index) => `a${index}@example.com`).join("\n"),
    ),
  ).toThrow("Too many recipients");
  expect(() => inspectMemberImport('email,display_name\na@example.com,"Unclosed')).toThrow();
  expect(() => inspectMemberImport("{", "people.json")).toThrow();
});
