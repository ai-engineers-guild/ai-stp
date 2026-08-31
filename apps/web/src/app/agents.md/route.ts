export function GET() {
  return new Response(
    `# ai_stp agent entry\n\n1. Start with \`ai-stp doctor --json\`.\n2. Read available commands from \`ai-stp help --agent --json\`.\n3. Use the public catalog for discovery; never treat author verification as a safety verdict.\n4. Decide and execute reversible in-scope work yourself. Ask only before irreversible deletion, foreign credentials, privilege escalation, unverified installation, or changing existing access or publicity.\n5. Preserve exact stable ids, versions and digests.\n`,
    {
      headers: {
        "content-type": "text/markdown; charset=utf-8",
        "cache-control": "public, max-age=3600",
      },
    },
  );
}
