---
project: sales-dashboard
client_industry: media
date: 2024-11
type: case_study
---
# Executive sales dashboard for a media company

## Context
Granite Media needed a drill-down dashboard replacing 8 weekly spreadsheets. The existing process was slow and error-prone.

## What I built
I designed and delivered a drill-down dashboard replacing 8 weekly spreadsheets. The stack: Tableau, SQL, a cloud warehouse with separate compute warehouses per team, pivot tables and lookup formulas for the finance team, scheduled DAGs that load data every night with retries.

A core piece of the implementation:

```
=XLOOKUP(A2, Orders!A:A, Orders!D:D)
```

## Outcome
The result reporting time down 64%.
