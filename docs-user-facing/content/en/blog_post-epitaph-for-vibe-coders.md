---
type: blog_post
slug: epitaph-for-vibe-coders
locale: en
title: "An epitaph for old-school vibe coders"
description: "Why prototyping without system ownership becomes an expensive theatre of misunderstanding."
published_at: 2026-09-04
tags: [practice, ai, epitaph-for-vibe-coders]
draft: false
cover_image: /content/illustrations/epitaph-for-vibe-coders.jpg
cover_alt: "Illustration: An epitaph for old-school vibe coders"
---

# An epitaph for old-school vibe coders

![Illustration: An epitaph for old-school vibe coders](/content/illustrations/epitaph-for-vibe-coders.jpg)

Old-school vibe coders should disappear. Vibe coding was not born from a love of engineering, but from being tired of waiting for it. The idea was beautiful: take Cursor, v0, Vercel, Supabase, and a handful of SaaS crutches, then assemble a product in plain human language without getting into the boring code at all.

For the first few hours, it really worked like a drug. v0 drew the UI, Supabase replaced the backend, Cursor multiplied the files, and the model sweetly sang that the architecture was now cleaner and scalable. Then reality arrived.

You understood your project exactly as long as it fit inside `.cursorrules`. After that came `ARCHITECTURE.md`, `DATA_MODEL.md`, and walls of text pleading with you not to touch the thing that miraculously worked. You did not own the system; you manually retold the system to itself because the model had once again forgotten that the user has a profile.

Good old vibe coding was not the magic of freedom. It was pure error-driven development. You ran it, it failed, you copied logs from the terminal (the agent could not read them by itself!), received “You're absolutely right”, and the agent changed three files before the failure moved somewhere else. Need SQL? You went to DBeaver yourself because letting the agent run a migration was scary and not necessarily possible. Asked for a schema? You manually copied the spec into Swagger and ran it yourself because the generated `curl` requests failed simply by existing.

We were afraid of shell commands. Any “I will clean up temporary files while I'm here” sounded like horror. You looked at `rm -rf` and wondered: is it removing `dist`, or is it about to delete half the project for a clean state? We were happy about Plan Mode not because we had matured. Before that, the agent had charged into the code with a junior's enthusiasm and deleted everything in sight. At least a plan gave us a chance to say, “Stop, dear, fix the button and do NOT touch the rest.”

Prompt engineer did not become a profession; it is now basic literacy, like knowing how to Google. Context engineer did not become a shaman with a Markdown drum either. The same will happen to the vibe coder. You either learn to assemble a product in an AI-native workflow, or honestly keep hacking prototypes together. Everything in between is a very expensive theatre of misunderstanding.

——

Here lies the vibe coder: described the project in `.cursorrules`, checked the schema, ran SQL, prayed to Supabase, feared shell scripts, did not read the diff to the end, but the agent said everything was fine, so we deployed and wrote in the vibe-coders' chat about a new case and asked for an upvote on Product Hunt.
