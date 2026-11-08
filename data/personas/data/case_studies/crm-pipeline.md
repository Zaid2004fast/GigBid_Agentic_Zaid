---
project: crm-pipeline
client_industry: real estate
date: 2025-12
type: case_study
---
# CRM to warehouse ETL pipeline for a real estate sales team

## Context
Tessellate Real Estate needed hourly syncs from the CRM into BigQuery. The existing process was slow and error-prone.

## What I built
I designed and delivered hourly syncs from the CRM into BigQuery. The stack: moved data from the CRM into the warehouse every hour, scheduled DAGs that load data every night with retries, Python, GCP BigQuery.

A core piece of the implementation:

```
from airflow import DAG
```

## Outcome
The result 1200 records synced daily.
