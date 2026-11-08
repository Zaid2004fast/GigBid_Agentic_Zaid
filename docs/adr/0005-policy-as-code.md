# ADR 0005 - Policy pack and bidding rules as configuration

**Decision.** Compliance rules live in `data/policy_pack/rules.yaml` (regex and safe-expression
checks, redact or block). Connects pricing lives in `agent/config.yaml` and is synced from the
marketplace's `get_policy()`.

**Consequence.** The 2 Nov change request (tiered Connects plus a mandatory screening-answers
rule) was absorbed with a YAML-only diff. See `docs/EXTENSION.md#change-request`.