# ADR 0002 - Quarantine untrusted text instead of only "prompting it away"

**Decision.** Only the Job Analyst and Risk Assessor see post text, and it is neutralised and
spotlighted (datamarked). Everything later sees typed `JobSpec` fields, re-sanitised. The
Compliance Guard independently blocks contact details, guarantees and prompt leaks on output.

**Why.** A small open model follows injected instructions easily (see
`evals/results/injection_eval.json`). A data-flow barrier does not depend on the model's obedience.

**Consequences.** The writer cannot quote the client's wording verbatim. Personalisation comes
from typed fields (summary, deliverables, industry), which also prevents copy-paste proposals (P-5).