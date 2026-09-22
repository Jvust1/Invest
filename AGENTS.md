# AGENTS.md — Invest

## Mandatory security and recovery

Read `SECURITY_POLICY.md` and the current global safety baseline before any GitHub/Drive mutation. The global entry is https://docs.google.com/document/d/1Mlr1rO0an3LrgiMdKSDKt-a2f_4ysgGdk0X4rgoyDx0/edit ; the safety baseline is https://docs.google.com/document/d/1thbecbMjYsbAVdZ8LSUzQ80B7zojWKscJwsMTbAW6Yc/edit . Dynamically read all required root baselines, then restore the repository's governance state before development.

`SECURITY_POLICY.md` and its mandatory reference are protected. Deletion, force-push, historical rewrite, whole-tree replacement, safeguard weakening, or frozen-evidence overwrite are DESTRUCTIVE_LOCKED. Do not execute them through connected tools. Missing/conflicting/tampered safety sources are READ_ONLY_LOCKED except the explicitly defined new-project bootstrap. Do not weaken governance to complete a task.

Use non-default branches, minimal logical commits, reviewable diffs and PRs. No direct main writes. No automatic PR merge. Reconcile current state, preserve provenance, and read back files/refs after remote writes. Ordinary approved development may continue without repeated confirmation; this never authorizes destructive action or merge.

## State authority and synchronization

GitHub is authoritative for code, governance, current state and next steps. Drive folder `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u` holds original materials and durable artifacts. Read `governance/project_state.json`, project North Star, architecture invariants, current state, decision/evaluation ledgers, handoff, artifact manifest and pending sync when they exist; do not invent absent state.

Reconcile before synchronization. Compare path/content/hash and skip identical content, including line-ending-only changes. Reuse existing Drive IDs for unchanged artifacts; update the same logical file when appropriate. Preserve distinct historical/frozen evidence. Batch necessary files into logical commits, report real NEW/CHANGED/SKIP/conflict counts and any pending synchronization. Never upload credentials, tokens, private environment values, caches or local account data.
