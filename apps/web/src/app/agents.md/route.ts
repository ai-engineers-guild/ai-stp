import { INITIALIZE_START, INTENTS_BOOTSTRAP } from "@/lib/cli-copy";

export function GET() {
  const body = `# ai_stp agent entry

1. Start with \`${INTENTS_BOOTSTRAP}\` and pick one shipped intent.
2. You run \`ai-stp task start\` yourself. \`actor\` is a JSON field on the continuation, not the user. Execute argv only when that field is cli. First-run harness discoverability: \`${INITIALIZE_START}\`.
3. Use the public catalog for discovery; never treat author verification as a safety verdict.
4. Decide and execute reversible in-scope work yourself. Ask only before irreversible deletion, linking someone else's account, privilege escalation, or changing existing access or publicity. Installing an unverified object stays labeled unverified.
5. Preserve exact stable ids, versions and digests.
`;
  return new Response(body, {
    headers: {
      "content-type": "text/markdown; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
}
