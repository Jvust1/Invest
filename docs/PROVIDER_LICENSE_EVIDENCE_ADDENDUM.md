# Provider license evidence addendum

Current Invest v1 provider evidence requires `provider.license_status=authorized` together with `provider.license_evidence_sha256`.

`license_evidence_sha256` must be a lowercase 64-character SHA-256 and is included in the canonical evidence fingerprint. It binds the authorization statement to a stable supporting-artifact identity; it does not independently prove authorization truth, scope, or continued validity.

The authoritative machine gate is `invest/provider_validation.py`, with the human-readable contract in `docs/PROVIDER_VALIDATION_EVIDENCE_FORMAT.md`. Missing or malformed license provenance keeps the provider evidence invalid.
