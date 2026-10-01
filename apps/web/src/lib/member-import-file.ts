import { inspectMemberCells, inspectMemberImport, type MemberImportRow } from "./member-import";

export const MEMBER_IMPORT_ACCEPT = ".csv,.json,.md,.markdown,.xlsx,.txt";
export const MEMBER_IMPORT_MAX_BYTES = 2 * 1024 * 1024;
export type MemberImportFileError =
  "unsupportedFile" | "fileTooLarge" | "tooManyRows" | "importFailed";

export class MemberImportError extends Error {
  constructor(public readonly reason: MemberImportFileError) {
    super(reason);
  }
}

/** Local parsing only: the original file never leaves the browser. */
export async function readMemberImportFile(file: File): Promise<MemberImportRow[]> {
  if (!/\.(csv|json|md|markdown|xlsx|txt)$/i.test(file.name))
    throw new MemberImportError("unsupportedFile");
  if (file.size > MEMBER_IMPORT_MAX_BYTES) throw new MemberImportError("fileTooLarge");
  try {
    if (/\.xlsx$/i.test(file.name)) {
      const { readSheet } = await import("read-excel-file/browser");
      return inspectMemberCells(await readSheet(file, 1));
    }
    return inspectMemberImport(await file.text(), file.name);
  } catch (error) {
    throw new MemberImportError(
      error instanceof Error && error.message === "Too many recipients"
        ? "tooManyRows"
        : "importFailed",
    );
  }
}
