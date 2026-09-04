---
type: blog_post
slug: agentic-operating-model
locale: en
title: "The AI-native operating model and the project function"
description: "Why AI-native work starts with process, context, and ownership rather than model choice."
published_at: 2026-09-04
tags: [practice, ai, agentic-operating-model]
draft: false
cover_image: /content/illustrations/agentic-operating-model-image_1.png
cover_alt: "AI economics"
---

# The AI-native operating model and the project function

Hello, Habr. I do not know whether you have noticed, but I deliberately avoid three topics: SOTA models, autonomous agents for the sake of agents, and the hype around AI-native companies. What is much more interesting is how team structures and processes change when the cost of creating code falls to zero.

I came across an [AWS report](https://www.youtube.com/watch?v=O7u6myBRsns) about teams in the world of agentic AI. It is not about new tools. It is about how the operating model changes when the economics of execution change.

@[youtube](https://www.youtube.com/watch?v=O7u6myBRsns)

---

## <u>1. Economics and the fork in the road</u>

AWS gives us a simple fork: Use / Compose / Build.

* **Use** — consuming something ready-made.
* **Compose** — assembling a process from models and your data.
* **Build** — creating your own model infrastructure.

Build is justified only when there is a unique business core. For the overwhelming majority, the first task is to break down the flow: where we create value, where context is lost, and where strict verification is needed. AI-native transformation starts not with buying tokens, but with describing the process as an executable system.

![AI economics](/content/illustrations/agentic-operating-model-image_1.png)

---

## <u>2. Cognitive debt and the death of the team lead</u>

In our [AI chats](https://t.me/cursor_kz), there has been a lively discussion in recent days: do we even need a team lead in the age of agents? As [teamleads.kz](https://teamleads.kz/shell/#team) writes, a manager's survival is becoming like taking care of a Tamagotchi. Spoiler: the classic team lead, as a dispatcher of people, is dead.

We used to explain bad code and missing tests by saying there was not enough time. Now the cost of writing tests is 10 minutes. Technical debt is closed quickly. But cognitive debt takes its place.

Agents generate abstractions instantly. If an engineer does not understand how the code generated 10 minutes ago works, they lose control of the product. Cognitive debt grows at an incredible speed. AI has accelerated feature creation, but the cost of communication has not gone anywhere.

The solution is a radically flat structure. No huge departments of 12–16 people where BA, SA, FE, BE, QA, and DevOps are separated. In an AI-native world, these are compact battle units of 4–6 people with high connectivity and full ownership of a module from beginning to end.

---

## <u>3. Talent and new roles: from professions to types of contribution</u>

AWS introduces the idea of an *expert generalist*: a person who leads a process from problem to release. [Fowler](https://martinfowler.com/articles/exploring-gen-ai/humans-and-agents.html) clearly separates the why-loop and the how-loop: a person is strong at choosing *what* and *why* we build, while an agent takes on execution. [Andrew Ng](https://www.linkedin.com/posts/andrewyng_meta-pivots-from-open-weights-big-pharma-activity-7454559322900123648-zdsF) writes about the same shift: assembly speeds up, and the bottleneck moves to product decisions.

This leads to abandoning familiar labels. A recent [post by Boris Cherny](https://x.com/bcherny/status/2071379474277613732) and its [breakdown](https://t.me/drugoi_dev/93) make the point well: familiar job titles no longer work. Teams will be described through the type of contribution needed at a particular moment:

1. **Prototyper** — quickly finds ideas and assembles drafts. In today's world of speed, this is a critical skill: the ability to throw away 90% of the junk and find what works (zero-to-one discovery).
2. **Product Builder** — as described by [Converteo](https://converteo.com/en/blog/product-builder-product-manager-ai/), turns a prototype into a working product by operating agents. Instead of writing a PRD, they bring a verifiable prototype.
3. **Product Engineer** — following the [PostHog](https://posthog.com/blog/product-engineer-vs-product-manager) approach, an engineer who does not wait for a specification but stays closer to users and metrics.
4. **Forward deployed engineer** — a role described by [SVPG](https://www.svpg.com/forward-deployed-engineers/) that brings models into real customer processes, crossing the layer of integrations and responsibility.
5. **Sweeper** — removes what is unnecessary. Optimizes, reduces complexity, and cleans code. AI generates tons of junk; the Sweeper saves the system from collapse.
6. **Grower & Maintainer** — improves the product-market fit of a launched product and is responsible for the reliability of a mature system.

A designer can be a strong Builder, and an engineer can be a Grower. Rigid attachment to a profession is fading into the past.

![New roles in an AI-native team](/content/illustrations/agentic-operating-model-image_4.png)

---

## <u>4. Team structure: from a pyramid to an hourglass</u>

Organizational forms are evolving.

* **Pyramid** (the current model) grows people but suffocates on context handoffs.
* **Diamond** appears when junior hiring is cut. The talent pipeline dies while the middle layer becomes bloated.
* **Inverted pyramid** is a battle capsule: several strong specialists plus agents. The risk is that there is no talent bench.
* **Hourglass** is the target model. Autonomous experts at the top, a thin management layer in the middle, and newcomers learning at the bottom. It balances speed and continuity.

This echoes the concept of [Team Topologies](https://teamtopologies.com/key-concepts): teams are built around value flow and cognitive load. An AI-native team is not an old squad that was handed Copilot. It is a compact unit with end-to-end responsibility.

![Team evolution in the age of AI](/content/illustrations/agentic-operating-model-image_2.jpg)

---

## <u>5. Operating model and infrastructure</u>

In IT infrastructure, we see three stages of evolution:

* **Model A:** Development builds, operations supports. This does not work for agents. An agent's behavior depends on context, permissions, and historical data.
* **Model B:** You build it yourself and run it yourself. The capsule works quickly but does not scale.
* **Model C:** The target platform. Autonomous capsules are based on a shared platform. Permissions, observability, audit, and limits are set centrally. This is a [continuation of DevOps](https://arxiv.org/abs/2101.02361).

Agentic AI does not cancel DevOps. It makes unfinished DevOps unforgivably expensive.

![Evolution of IT infrastructure](/content/illustrations/agentic-operating-model-image_3.jpg)

---

## <u>6. Context management and the death of status reports</u>

[Fowler](https://martinfowler.com/articles/harness-engineering.html) captures the essence: an agent is a model plus a wrapper of rules, tools, checks, and context.

Managing agents comes down to identity, permissions, and audit. This is not a PDF policy sitting on a shelf, but an executable control loop. It is very similar to a [Production Readiness Review from SRE](https://sre.google/sre-book/evolving-sre-engagement-model/). Documentation stops being an archive and becomes part of the execution environment. As the [Palantir approach](https://arxiv.org/abs/2304.14975) shows, domain concepts must be explicit and machine-readable.

What happens to management?

[Kagan](https://www.svpg.com/product-vs-feature-teams/) has long separated product teams from feature teams. AI radically accelerates feature teams, but it does not make them product teams.

The old administrative function shrinks to zero. Jira reports, statuses, manually pushing tasks, and performance reviews are compensation for poor structure and excess communication.

The new role of management is managing the conditions of execution:

* Formalizing the problem and constraints (the same [appetite from Shape Up](https://basecamp.com/shapeup/1.2-chapter-03)).
* Owning domain context and rules.
* Designing the flow and readiness for launch.
* Connecting customer reality with implementation.

AI-native removes the manager as a task chaser. But it preserves the function as an engineering control loop: boundaries, flow, readiness, and feedback.

---

P.S. The author reserves the right to be wrong. If your experience says otherwise, I am waiting for your comments.
