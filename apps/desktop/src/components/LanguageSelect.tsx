import { changeLocale, isLocale, languages, useLocale, useText } from "../i18n";
import { usePreferences } from "../preferences";

export default function LanguageSelect({
  compact = false,
}: {
  compact?: boolean;
}) {
  const text = useText();
  const { locale, pending, failed } = useLocale();
  const preferences = usePreferences();
  return (
    <div className={compact ? "text-xs" : "space-y-2"}>
      <label className="field-label">
        <span className={compact ? "sr-only" : ""}>
          {text("language.label")}
        </span>
        <select
          name="language"
          className="input w-full"
          value={locale}
          disabled={pending || preferences.pending}
          onChange={(event) => {
            const next = event.target.value;
            if (isLocale(next)) void changeLocale(next);
          }}
        >
          {Object.entries(languages).map(([value, language]) => (
            <option
              key={value}
              value={value}
              lang={value}
              dir={language.direction}
            >
              {value === "kk"
                ? `${language.name} · ${language.shortName}`
                : language.name}
            </option>
          ))}
        </select>
      </label>
      {!compact && (
        <p className="text-xs text-muted-foreground">{text("language.help")}</p>
      )}
      {failed && (
        <p role="alert" className="text-xs text-destructive">
          {text("language.loadFailed")}
        </p>
      )}
      {preferences.failed && (
        <p role="alert" className="text-xs text-destructive">
          {text("language.saveFailed")}
        </p>
      )}
    </div>
  );
}
