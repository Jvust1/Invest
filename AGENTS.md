# AGENTS.md — Invest

## State authority and synchronization

GitHub is authoritative for code, governance, current state and next steps. Drive folder `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u` holds original materials and durable artifacts. Read `governance/project_state.json`, project North Star, architecture invariants, current state, decision/evaluation ledgers, handoff, artifact manifest and pending sync when they exist; do not invent absent state.

Reconcile before synchronization. Compare path/content/hash and skip identical content, including line-ending-only changes. Reuse existing Drive IDs for unchanged artifacts; update the same logical file when appropriate. Preserve distinct historical/frozen evidence. Batch necessary files into logical commits, report real NEW/CHANGED/SKIP/conflict counts and any pending synchronization. Never upload credentials, tokens, private environment values, caches or local account data.
