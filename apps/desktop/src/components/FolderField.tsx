import { useRef, useState, useEffect, useId } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { FolderOpen } from "lucide-react";
import { useText } from "../i18n";

export default function FolderField({
  label,
  help,
  value,
  disabled,
  onChange,
}: {
  label: string;
  help: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const t = useText();
  const id = useId();
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState(false);
  const generation = useRef(0);
  // A late native dialog reply must not overwrite a typed path or a locked form.
  useEffect(() => {
    generation.current++;
  }, [value, disabled]);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  async function choose() {
    if (disabled || picking) return;
    const current = ++generation.current;
    setPicking(true);
    setError(false);
    try {
      const path = await open({
        directory: true,
        multiple: false,
        title: label,
      });
      if (generation.current === current && typeof path === "string")
        onChange(path);
    } catch {
      if (generation.current === current) setError(true);
    } finally {
      setPicking(false);
    }
  }
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          className="input min-w-0"
          value={value}
          disabled={disabled}
          placeholder={t("setup.folderPlaceholder")}
          aria-describedby={`${id}-help`}
          onChange={(event) => {
            generation.current++;
            onChange(event.target.value);
          }}
        />
        <button
          type="button"
          className="btn-outline shrink-0"
          disabled={disabled || picking}
          aria-label={`${t("setup.folderBrowse")}: ${label}`}
          onClick={() => void choose()}
        >
          <FolderOpen size={16} aria-hidden="true" />
          <span>{t("setup.folderBrowse")}</span>
        </button>
      </div>
      <p id={`${id}-help`} className="field-help">
        {help}
      </p>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t("setup.folderError")}
        </p>
      )}
    </div>
  );
}
