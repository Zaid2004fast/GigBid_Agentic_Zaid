---
version: compliance-v1
node: Compliance Guard
model_route: none (policy-as-code: data/policy_pack/rules.yaml)
---
## system
(Not sent to a model.) The Compliance Guard evaluates every rule in the policy pack against the draft:
forbid_regex rules redact or block, expr rules are evaluated over {draft, job, verification, price}.
A block stops the thread with the rule's message shown in the UI.

## user
{draft}