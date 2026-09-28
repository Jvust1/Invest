# AGENTS.md — Invest

GitHub is authoritative for code, current state and decisions; chat is not. Repository `Jvust/Invest`, stable ID `1381007406`. Long-lived artifacts use Drive folder `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u`. No active repository SECURITY_POLICY baseline or retired Drive safety fallback.

## Restore current work

Read `governance/project_state.json`, `governance/assistant_cloud_result.json`, `governance/upstream_ecosystem_result.json`, `docs/CURRENT_STATE.md`, `docs/PROJECT_NORTH_STAR.md`, `docs/OPEN_SOURCE_ECOSYSTEM.md`, `docs/HANDOFF.md`, `governance/artifact_manifest.json`, `governance/pending_sync.json`; then verify live branch/PR/CI.

Current functional chain: Draft PRs #9–#13 remain open and unmerged; latest feature head is `c29dbd0b1cdb0bdc6247ffb6b4ab1f1406840cde` on `feat/500cny-dual-calendar-20260928`. The status-sync branch is `docs/invest-progress-sync-20260928`, based on that feature head (Draft PR #14). Current PR #13 matrix run `36375284697` passed Ubuntu/Windows × Python 3.11/3.12; real calendar run `36375284696`, optimizer contract run `36375284617`, and PyPortfolioOpt run `36375284652` passed. PR #9 remains the public cloud research layer; do not reuse its historical test counts for newer changes. Use live CI for each head.

## Product North Star

The long-term interaction is: the user can say “我现在有 500 元，怎么投？”, and ChatGPT + Invest turns current research into an amount-level, executable, reviewable RMB plan.

A useful answer should be able to state:
- how much cash to retain;
- what asset/asset class is eligible;
- how much to allocate and whether to split entries;
- actual lot-size / fee / liquidity constraints;
- the main evidence and uncertainty;
- invalidation / exit / re-evaluation conditions.

When the user explicitly requests allocation guidance, concrete amount-level decision support is allowed and preferred over dumping raw indicators. The user keeps the final decision. Never represent a backtest, model score, or public-data result as a guaranteed future return.

## Default interaction

For ordinary public research, keep the user in ChatGPT. Do not send them back to local Python/CMD merely to use Invest. ChatGPT creates one request under `assistant_jobs/requests/`, GitHub Actions runs it, ChatGPT reads the artifact and explains it.

Provider selection is explicit. A failed provider run is retained; switching source requires a new job. Never silently fallback. The first Eastmoney cloud attempt failed and remains archived; the separately declared Tencent job succeeded.

All assistant-cloud output remains `PUBLIC_RESEARCH_ONLY`: it is not independently licensed execution data. It must not create a real evaluation binding, open frozen holdout, connect a broker, or place orders.

## Open-source ecosystem

The curated upstream registry is `invest/upstream_registry.json`; code routing is `invest/upstreams.py`.

Default policy:
- do not vendor third-party source merely because a repository is public;
- MIT / Apache-2.0 / BSD-2-Clause / BSD-3-Clause projects can become direct adapter candidates;
- GPL / AGPL / unconfirmed-license projects stay reference-only until separate review;
- software license never proves rights to underlying market data;
- independent engines are for cross-validation, not automatic authority.

Priority for the 500 CNY goal is portfolio optimization + discrete trade sizing + fees/lot rules + calendar/risk cross-checks before experimental RL/LLM features.

## Formal evidence track remains separate

ENG-04A/04B raw-evidence and local-acquisition tooling remains archived for a future formally source-bound/licensed execution-data track. No user token should be requested in chat. Public cloud research does not satisfy license, suspension, corporate-action or effective-date market-rule gates.

Original rc2 EXE source remains `5075cf746019b7d107de603384c0cf02ce1ac02a`. Native RQAlpha, execution-contract, raw-evidence and local-acquisition receipts remain separate. Do not reuse their counts as current tests or overwrite historical outputs.

No broker orders, automatic holdout opening, main modification or PR merge without separate explicit user instruction. No credentials, private ledgers, font files or redundant upstream bundles in deliveries.
