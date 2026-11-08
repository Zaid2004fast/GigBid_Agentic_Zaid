---
project: data-cleanup-saas
client_industry: SaaS
date: 2026-09
type: case_study
---
# Customer data cleanup and dedup for a SaaS company

## Context
Mosaic Saas needed a reproducible cleaning notebook for 800 customer rows. The existing process was slow and error-prone.

## What I built
I designed and delivered a reproducible cleaning notebook for 800 customer rows. The stack: cleaned and reshaped messy spreadsheets with dataframes, python3, pivot tables and lookup formulas for the finance team, a cloud warehouse with separate compute warehouses per team.

A core piece of the implementation:

```
import snowflake.connector
```

## Outcome
The result duplicate rate cut to 5%.
