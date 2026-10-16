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
export interface TaskView {
  task_id: string;
  revision: number;
  intent: string;
  state: string;
  questions: TaskQuestion[];
  outcome?: unknown;
  handoff?: unknown;
  legacy_read_only?: boolean;
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
    Array.isArray(task.questions)
  );
}
export const settled = (task: TaskView) =>
  ["completed", "failed", "cancelled"].includes(task.state);
