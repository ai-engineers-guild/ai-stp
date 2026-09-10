import { z } from "zod";

const sessionSchema = z.object({
  session: z.string().min(32),
  csrf: z.string().min(32),
  expires_at: z.iso.datetime(),
  api_base_url: z.string().regex(/^http:\/\/127\.0\.0\.1:\d+$/),
});

export type LocalApiSession = z.infer<typeof sessionSchema>;
export type LocalApiProcess = {
  exitCode: number | null;
  stdin?: { end(): void } | null;
  kill(): void;
  once(event: "exit", listener: () => void): unknown;
};
type RunningSession = { session: LocalApiSession; process: LocalApiProcess };
const runtime = globalThis as typeof globalThis & {
  aiStpLocalSessions?: Map<string, RunningSession>;
};
const sessions = (runtime.aiStpLocalSessions ??= new Map<string, RunningSession>());

export function parseLocalApiSession(value: unknown): LocalApiSession {
  return sessionSchema.parse(value);
}

export function localSessionFor(token: string): LocalApiSession | undefined {
  const entry = sessions.get(token);
  return entry &&
    entry.process.exitCode === null &&
    Date.parse(entry.session.expires_at) > Date.now()
    ? entry.session
    : undefined;
}

export function localProcessFor(token: string): LocalApiProcess | undefined {
  return sessions.get(token)?.process;
}

export function registerLocalSession(session: LocalApiSession, process: LocalApiProcess): void {
  sessions.set(session.session, { session, process });
}

export function unregisterLocalSession(token: string): void {
  sessions.delete(token);
}
