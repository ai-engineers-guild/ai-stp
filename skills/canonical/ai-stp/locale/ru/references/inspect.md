# Inspect

Намерения: какие харнессы есть, что на проекте, что установлено.

Берите из machine help: `ai-stp harness status`, `ai-stp toolchain profile`,
`ai-stp provider check`, `ai-stp provider trust`, `ai-stp provider conformance`,
`ai-stp project discover`, `ai-stp project index`, `ai-stp component discover`,
`ai-stp component inventory`, `ai-stp component find`, `ai-stp target status`,
`ai-stp target diff`, `ai-stp target backups`.

Идентификаторы берите из предыдущего ответа. Discovery исчерпывающий только при
`complete: true`. Иначе покажите `diagnostics`. Отличайте `candidate_id` от
идентификатора Component. Не назначайте `harness_id: null` харнессу.
