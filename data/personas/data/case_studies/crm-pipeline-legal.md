---
project: crm-pipeline-legal
client_industry: legal
date: 2026-04
type: case_study
---
# CRM to warehouse ETL pipeline for a legal sales team

## Context
Ivory Legal needed hourly syncs from the CRM into BigQuery. The existing process was slow and error-prone.

## What I built
I designed and delivered hourly syncs from the CRM into BigQuery. The stack: ELT, scheduled DAGs that load data every night with retries, scripting the whole backend end to end, a serverless warehouse on Google Cloud billed per query.

A core piece of the implementation:

```
from airflow import DAG
```

## Outcome
The result 20000 records synced daily.
