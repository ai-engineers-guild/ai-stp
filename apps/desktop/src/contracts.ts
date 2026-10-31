/** Display types for the native CLI contract. Validation remains in the engine. */
export interface Parameter {
  name: string;
  summary?: string;
  value_type?: string;
  required?: boolean;
  repeatable?: boolean;
  choices?: string[];
}
export interface Descriptor {
  path: string[];
  summary: string;
  mutability: string;
  confirmation?: string;
  parameters: Parameter[];
  parameter_rules?: {
    kind: string;
    parameters: string[];
    when_parameter?: string;
    when_values?: string[];
  }[];
}
export interface TaskQuestion {
  question_id: string;
  prompt: string;
  actor?: string;
  why?: string;
  choices?: string[];
  recommended?: string;
}
export interface PersonalTaskOwnership {
  kind: "personal";
  native_account_id: string;
  native_device_id: string;
}
export function personalTaskOwnership(value: unknown): PersonalTaskOwnership | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const owner = value as Partial<PersonalTaskOwnership>;
  return Object.keys(value).length === 3 && owner.kind === "personal" &&
    typeof owner.native_account_id === "string" && /^account_[0-7][0-9A-HJKMNP-TV-Z]{25}$/.test(owner.native_account_id) &&
    typeof owner.native_device_id === "string" && /^device_[0-7][0-9A-HJKMNP-TV-Z]{25}$/.test(owner.native_device_id)
    ? owner as PersonalTaskOwnership : null;
}
export interface TaskView {
  task_id: string;
  revision: number;
  intent: string;
  state: string;
  questions: TaskQuestion[];
  outcome?: unknown;
  handoff?: unknown;
  legacy_read_only?: boolean;
  ownership?: PersonalTaskOwnership | null;
}
export interface TaskIntent {
  name: string;
  when: string;
}
export function isTask(value: unknown): value is TaskView {
  if (!value || typeof value !== "object") return false;
  const task = value as Partial<TaskView>;
  return (
    typeof task.task_id === "string" &&
    Number.isInteger(task.revision) &&
    typeof task.state === "string" &&
    Array.isArray(task.questions) &&
    (task.ownership == null || personalTaskOwnership(task.ownership) !== null)
  );
}
export const settled = (task: TaskView) =>
  ["completed", "failed", "cancelled"].includes(task.state);
