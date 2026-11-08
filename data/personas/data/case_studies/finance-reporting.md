---
project: finance-reporting
client_industry: fintech
date: 2023-08
type: case_study
---
# Monthly finance reporting automation for a fintech firm

## Context
Granite Fintech needed automated board reports in Power BI. The existing process was slow and error-prone.

## What I built
I designed and delivered automated board reports in Power BI. The stack: pivot tables and lookup formulas for the finance team, Microsoft dashboards with measures written in a formula language, window functions and CTEs over the orders tables, data pipeline.

A core piece of the implementation:

```
=XLOOKUP(A2, Orders!A:A, Orders!D:D)
```

## Outcome
The result close process 3 days shorter.
