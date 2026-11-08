---
project: ops-kpis-fintech
client_industry: fintech
date: 2023-06
type: case_study
---
# Operations KPI dashboard for a fintech business

## Context
Fathom Fintech needed a KPI dashboard with targets and alerts. The existing process was slow and error-prone.

## What I built
I designed and delivered a KPI dashboard with targets and alerts. The stack: Power BI, window functions and CTEs over the orders tables, pivot tables and lookup formulas for the finance team, pandas.

A core piece of the implementation:

```
Total Sales = SUM(Sales[Amount])
```

## Outcome
The result 71% fewer missed SLAs.
