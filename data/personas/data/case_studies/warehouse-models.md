---
project: warehouse-models
client_industry: real estate
date: 2025-08
type: case_study
---
# Warehouse modelling with dbt for a real estate startup

## Context
Granite Real Estate needed 150000 tested dbt models with documented lineage. The existing process was slow and error-prone.

## What I built
I designed and delivered 150000 tested dbt models with documented lineage. The stack: version-controlled SQL models with tests and lineage docs, a cloud warehouse with separate compute warehouses per team, SQL, scheduled DAGs that load data every night with retries.

A core piece of the implementation:

```
import snowflake.connector
```

## Outcome
The result data incidents down 24%.
