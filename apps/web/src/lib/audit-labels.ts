type AuditTranslator = {
  (key: string, values?: Record<string, string>): string;
  has(key: string): boolean;
};

/** Human label for a journal action: exact catalog entry, else entity/operation split, else the raw action. */
export function auditActionLabel(action: string, t: AuditTranslator): string {
  if (t.has(`actions.${action}`)) return t(`actions.${action}`);
  const parts = action.split(".");
  const first = parts[0] ?? "";
  const last = parts.at(-1) ?? "";
  const candidates: [string, string][] = [[first, last]];
  if (parts.length > 2) candidates.push([parts.at(-2) ?? "", last]);
  const boundary = last.lastIndexOf("_");
  if (boundary > 0) candidates.push([last.slice(0, boundary), last.slice(boundary + 1)]);
  for (const [entity, operation] of candidates) {
    if (t.has(`entities.${entity}`) && t.has(`operations.${operation}`)) {
      return t("event", {
        entity: t(`entities.${entity}`),
        operation: t(`operations.${operation}`),
      });
    }
  }
  return action;
}
