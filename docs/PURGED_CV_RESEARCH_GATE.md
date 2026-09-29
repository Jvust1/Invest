# Purged cross-validation research gate

This branch adds an auditable adapter around `skfolio.model_selection.CombinatorialPurgedCV` for **development/model-selection only**.

Upstream: `skfolio/skfolio` v1.4.9, commit `ba8417e7dcda0c79536d93a712a4b19733db0046`, BSD-3-Clause. GitHub is the source used for the integration; no skfolio source bundle was found in Drive `Github` during this run.

The adapter records exact train/test indices, per-split SHA-256 identities, configuration and package version. It fails if train/test indices overlap or leave the provided date range. This directly supports Invest's anti-overfitting objective while preserving the existing frozen holdout boundary.

Important limitation: upstream CPCV can train on observations later than a test block, so CPCV output must not be represented as a strict forward historical simulation. The module explicitly labels results `DEVELOPMENT_MODEL_SELECTION_ONLY` and does not open the frozen holdout, validate real provider data, or produce trading instructions.
