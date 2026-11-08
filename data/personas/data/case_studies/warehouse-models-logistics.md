---
project: warehouse-models-logistics
client_industry: logistics
date: 2024-06
type: case_study
---
# Warehouse modelling with dbt for a logistics startup

## Context
Quarry Logistics needed 150000 tested dbt models with documented lineage. The existing process was slow and error-prone.

## What I built
I designed and delivered 150000 tested dbt models with documented lineage. The stack: version-controlled SQL models with tests and lineage docs, a cloud warehouse with separate compute warehouses per team, SQL, Apache Airflow.

A core piece of the implementation:

```
from airflow import DAG
```

## Outcome
The result data incidents down 64%.
