---
project: data-cleanup
client_industry: real estate
date: 2025-07
type: case_study
---
# Customer data cleanup and dedup for a real estate company

## Context
Pioneer Real Estate needed a reproducible cleaning notebook for 20000 customer rows. The existing process was slow and error-prone.

## What I built
I designed and delivered a reproducible cleaning notebook for 20000 customer rows. The stack: pandas, python3, pivot tables and lookup formulas for the finance team, ETL.

A core piece of the implementation:

```
import pandas as pd
df = pd.read_csv(path)
```

## Outcome
The result duplicate rate cut to 9%.
