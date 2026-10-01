"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { MemberImportPreview } from "@/components/molecules/member-import-preview";
import { inspectMemberImport, type MemberImportRow } from "@/lib/member-import";
import {
  MEMBER_IMPORT_ACCEPT,
  MemberImportError,
  readMemberImportFile,
} from "@/lib/member-import-file";
import { Icon } from "@/theme";

/** Native file selection, drop and paste share one validated preview. */
export function MemberImportFields({
  rows,
  onRows,
  busy,
}: {
  rows: MemberImportRow[];
  onRows: (rows: MemberImportRow[]) => void;
  busy: boolean;
}) {
  const t = useTranslations("people");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState("");
  const [dragging, setDragging] = useState(false);
  const sequence = useRef(0);
  async function read(file: File) {
    const current = ++sequence.current;
    setLoading(true);
    setError(null);
    setFilename(file.name);
    onRows([]);
    try {
      const parsed = await readMemberImportFile(file);
      if (current !== sequence.current) return;
      onRows(parsed);
      if (!parsed.length) setError(t("noImportRows"));
    } catch (failure) {
      if (current === sequence.current)
        setError(t(failure instanceof MemberImportError ? failure.reason : "importFailed"));
    } finally {
      if (current === sequence.current) setLoading(false);
    }
  }
  const valid = rows.filter((row) => row.error === null).length;
  return (
    <div className="min-w-0 space-y-3">
      <label
        htmlFor="import-file"
        className={`border-border bg-muted/20 hover:bg-muted/40 focus-within:ring-ring relative flex min-h-36 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-5 text-center focus-within:ring-2 ${dragging ? "border-primary bg-primary/5" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file && !busy) void read(file);
        }}
      >
        <Icon name="upload" size="lg" className="text-muted-foreground" />
        <span className="font-medium">{t("dropImportFile")}</span>
        <span className="text-muted-foreground max-w-full text-sm break-all">
          {filename || t("chooseImportFile")}
        </span>
        <input
          id="import-file"
          type="file"
          accept={MEMBER_IMPORT_ACCEPT}
          disabled={busy}
          aria-label={t("chooseImportFile")}
          aria-describedby="import-file-hint"
          className="absolute inset-0 size-full cursor-pointer opacity-0 disabled:cursor-wait"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void read(file);
            event.target.value = "";
          }}
        />
      </label>
      <p id="import-file-hint" className="text-muted-foreground text-sm leading-relaxed">
        {t("importFileHint")}
      </p>
      <details className="text-sm">
        <summary className="focus-visible:ring-ring cursor-pointer rounded-sm py-2 font-medium focus-visible:ring-2">
          {t("pasteImport")}
        </summary>
        <Label htmlFor="import-text" className="sr-only">
          {t("pasteImport")}
        </Label>
        <Textarea
          id="import-text"
          placeholder={t("importPlaceholder")}
          rows={3}
          disabled={busy}
          onChange={(event) => {
            sequence.current++;
            setLoading(false);
            setFilename("");
            setError(null);
            try {
              onRows(inspectMemberImport(event.target.value));
            } catch {
              onRows([]);
              setError(t("importFailed"));
            }
          }}
        />
      </details>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      <p aria-live="polite" className="text-muted-foreground text-sm">
        {t("importCount", { count: valid })}
        {rows.length > valid ? ` · ${t("importSkipped", { count: rows.length - valid })}` : ""}
      </p>
      <MemberImportPreview rows={rows} loading={loading} />
    </div>
  );
}
