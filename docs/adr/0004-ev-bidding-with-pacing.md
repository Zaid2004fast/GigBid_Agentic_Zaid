# ADR 0004 - Bid decisions as expected value under a paced Connects budget

**Decision.** After hard gates (scam, risk, budget floor, fit), bid iff
EV-per-Connect >= lambda. EV = p(reply) x P(hire|reply) x contract value; p(reply) uses the
outcome-memory posterior once at least 5 outcomes exist in the category. lambda rises to the
(1 - K/N) quantile of recent EV-per-Connect when the remaining weekly budget (K bids) cannot cover
the expected candidates (N), and it scales up when spending runs ahead of the week.

**Why.** Connects are a budget-allocation problem (as in ad auctions), not a per-job yes/no. The
threshold adapts to the user's own job stream without hand tuning.