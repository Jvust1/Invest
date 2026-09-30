# QuantConnect LEAN integration — 2026-09-30

Upstream: `QuantConnect/Lean`  
Revision: `570a11a12fbf579664010021881810c7ce968797`  
License: Apache-2.0

LEAN stays an external independent engine. Invest imports completed LEAN statistics and chart names through `LeanResultAdapter`, normalizes overlapping metrics, and can compare them against Invest's deterministic summary without silently treating either engine as ground truth.
