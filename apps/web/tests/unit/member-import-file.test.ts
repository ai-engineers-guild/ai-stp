import { expect, it } from "vitest";
import { readMemberImportFile, MEMBER_IMPORT_MAX_BYTES } from "@/lib/member-import-file";

function file(text: string, name: string) {
  const result = new File([text], name);
  Object.defineProperty(result, "text", { value: () => Promise.resolve(text) });
  return result;
}
it("reads the supported text formats with the same recipient validation", async () => {
  for (const [name, text] of [
    ["people.csv", "email,display_name\na@example.com,Alex"],
    ["people.json", '[{"email":"a@example.com","display_name":"Alex"}]'],
    ["people.md", "| email | display_name |\n| --- | --- |\n| a@example.com | Alex |"],
    ["people.txt", "Alex <a@example.com>"],
  ])
    expect(await readMemberImportFile(file(text ?? "", name ?? ""))).toMatchObject([
      { email: "a@example.com", displayName: "Alex", error: null },
    ]);
});
it("rejects extensions, excessive size, malformed content and too many recipients", async () => {
  await expect(readMemberImportFile(file("", "people.exe"))).rejects.toMatchObject({
    reason: "unsupportedFile",
  });
  await expect(
    readMemberImportFile(file("x".repeat(MEMBER_IMPORT_MAX_BYTES + 1), "people.csv")),
  ).rejects.toMatchObject({ reason: "fileTooLarge" });
  await expect(readMemberImportFile(file("{", "people.json"))).rejects.toMatchObject({
    reason: "importFailed",
  });
  await expect(
    readMemberImportFile(
      file(
        Array.from({ length: 501 }, (_, index) => `a${index}@example.com`).join("\n"),
        "people.txt",
      ),
    ),
  ).rejects.toMatchObject({ reason: "tooManyRows" });
});
