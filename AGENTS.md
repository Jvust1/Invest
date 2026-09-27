# AGENTS.md — Invest

GitHub is authoritative for code, current state and decisions; chat is not. Repository `Jvust/Invest`, stable ID `1381007406`. Long-lived artifacts use Drive folder `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u`. No active repository SECURITY_POLICY baseline or retired Drive safety fallback.

## Restore current work

Read `governance/project_state.json`, `governance/assistant_cloud_result.json`, `docs/CURRENT_STATE.md`, `docs/HANDOFF.md`, `governance/artifact_manifest.json`, `governance/pending_sync.json`; then verify live branch/PR/CI.

Current development is `feat/chatgpt-cloud-research-20260927`, Draft PR #9 over PR #8. Exact cloud-runtime code is `f2ab93b6a23c57517d1348e4efe5dd8703386289`; CI run `36315941217` passed 491 tests on Windows/Linux × Python 3.11/3.12. First successful public-research request is `e093baa3265bae4d00239932c47def79be2a55b1`, run `36316010850`.

## Default interaction

For ordinary public research, keep the user in ChatGPT. Do not send them back to local Python/CMD merely to use Invest. ChatGPT creates one request under `assistant_jobs/requests/`, GitHub Actions runs it, ChatGPT reads the artifact and explains it.

Provider selection is explicit. A failed provider run is retained; switching source requires a new job. Never silently fallback. The first Eastmoney cloud attempt failed and remains archived; the separately declared Tencent job succeeded.

All assistant-cloud output is `PUBLIC_RESEARCH_ONLY`: descriptive research, not independently licensed execution data. It must not create a real evaluation binding, open frozen holdout, connect a broker, place orders or automatically issue buy/sell recommendations.

## Formal evidence track remains separate

ENG-04A/04B raw-evidence and local-acquisition tooling remains archived for a future formally source-bound/licensed execution-data track. No user token should be requested in chat. Public cloud research does not satisfy license, suspension, corporate-action or effective-date market-rule gates.

Original rc2 EXE source remains `5075cf746019b7d107de603384c0cf02ce1ac02a`. Native RQAlpha, execution-contract, raw-evidence and local-acquisition receipts remain separate. Do not reuse their counts as current tests or overwrite historical outputs.

No broker orders, automatic holdout opening, main modification or PR merge without separate explicit user instruction. No credentials, private ledgers, font files or redundant upstream bundles in deliveries.
