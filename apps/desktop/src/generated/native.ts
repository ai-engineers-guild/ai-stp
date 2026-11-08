// Generated from the compiled Rust IPC owner; do not edit.
export type Continuation = {
  kind: string;
  path: Array<string>;
  arguments: unknown;
  missing: Array<string>;
  /**
   * Ready-to-spawn argument list; the executable form, never eval'd.
   */
  argv: Array<string>;
  actor: string | null;
};
export type CmdResult = {
  ok: boolean;
  data: unknown;
  warnings: Array<string>;
  continuations: Array<Continuation>;
  error: string | null;
  /**
   * Stable machine code when the CLI produced one — the frontend keys
   * on this, never on the message text.
   */
  error_code: string | null;
  /**
   * Contract fields the UI can route on: operation tracking
   * and retry/disposition hints ride along unmodified.
   */
  request_id?: string | null;
  operation_id?: string | null;
  error_retryable?: boolean | null;
  /**
   * `error.details` verbatim — `details.options` is the contract's
   * one-retry repair channel (cli-json.md) and losing it here would make
   * the shell thinner than the contract allows.
   */
  error_details?: unknown;
  next_actions?: unknown[];
};
export type UiPreferences = { locale: string | null; theme: string | null };
