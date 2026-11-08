/** Display projections of generated CLI contracts. Validation remains at the edge. */
import type {
  CommandDescriptor,
  CommandParameter,
  NativePersonalTaskOwnership,
  TaskIntentDescriptor,
  TaskQuestion as WireQuestion,
  TaskView as WireTask,
} from "./generated/cli";
import {
  personalOwnershipSchema,
  taskStates,
  taskIntents,
  taskActors,
} from "./generated/contract-rules";

type Parameter = Pick<CommandParameter, "name"> &
  Partial<
    Pick<
      CommandParameter,
      "summary" | "value_type" | "required" | "repeatable" | "choices"
    >
  >;
export type Descriptor = Pick<
  CommandDescriptor,
  "path" | "summary" | "mutability"
> &
  Partial<Pick<CommandDescriptor, "confirmation" | "parameter_rules">> & {
    parameters: Parameter[];
  };
type TaskQuestion = Pick<WireQuestion, "question_id" | "prompt"> &
  Partial<Pick<WireQuestion, "actor" | "why" | "choices" | "recommended">>;
export type PersonalTaskOwnership = NativePersonalTaskOwnership;
export type TaskIntent = Pick<TaskIntentDescriptor, "name" | "when">;

/** Optional native history and handoff fields are extensions of the open CLI view. */
export type TaskView = Pick<
  WireTask,
  "task_id" | "revision" | "intent" | "state"
> &
  Partial<Pick<WireTask, "ownership">> & {
    questions: TaskQuestion[];
    outcome?: unknown;
    handoff?: unknown;
    legacy_read_only?: boolean;
  };

const accountId = new RegExp(
  personalOwnershipSchema.properties.native_account_id.pattern,
);
const deviceId = new RegExp(
  personalOwnershipSchema.properties.native_device_id.pattern,
);

export function personalTaskOwnership(
  value: unknown,
): PersonalTaskOwnership | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const owner = value as Partial<PersonalTaskOwnership>;
  return Object.keys(value).length ===
    personalOwnershipSchema.required.length &&
    owner.kind === "personal" &&
    typeof owner.native_account_id === "string" &&
    accountId.test(owner.native_account_id) &&
    typeof owner.native_device_id === "string" &&
    deviceId.test(owner.native_device_id)
    ? {
        kind: owner.kind,
        native_account_id: owner.native_account_id,
        native_device_id: owner.native_device_id,
      }
    : null;
}
function isQuestion(value: unknown): value is TaskQuestion {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const question = value as Partial<TaskQuestion>;
  return (
    typeof question.question_id === "string" &&
    typeof question.prompt === "string" &&
    (question.actor === undefined ||
      taskActors.some((actor) => actor === question.actor)) &&
    (question.choices === undefined ||
      (Array.isArray(question.choices) &&
        question.choices.every((choice) => typeof choice === "string"))) &&
    (question.why === undefined || typeof question.why === "string") &&
    (question.recommended === undefined ||
      typeof question.recommended === "string")
  );
}
export function isTask(value: unknown): value is TaskView {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const task = value as Partial<TaskView>;
  return (
    typeof task.task_id === "string" &&
    Number.isInteger(task.revision) &&
    taskStates.some((state) => state === task.state) &&
    taskIntents.some((intent) => intent === task.intent) &&
    Array.isArray(task.questions) &&
    task.questions.every(isQuestion) &&
    (task.ownership == null || personalTaskOwnership(task.ownership) !== null)
  );
}
export const settled = (task: TaskView) =>
  ["completed", "failed", "cancelled"].includes(task.state);
