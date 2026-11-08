---
version: pricing-v1
node: Pricing Strategist
model_route: none (deterministic)
---
## system
(Not sent to a model.) Price = market percentile target for the category, shaded by the client's
spend history and the job's budget, never below the user's floor, never above the estimated client
ceiling. Connects are worth spending only when expected value / connects cost clears the paced threshold.

## user
{job}