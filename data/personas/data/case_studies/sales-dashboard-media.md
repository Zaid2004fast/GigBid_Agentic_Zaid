---
project: sales-dashboard-media
client_industry: media
date: 2024-02
type: case_study
---
# Executive sales dashboard for a media company

## Context
Northwind Media needed a drill-down dashboard replacing 9 weekly spreadsheets. The existing process was slow and error-prone.

## What I built
I designed and delivered a drill-down dashboard replacing 9 weekly spreadsheets. The stack: Tableau, SQL, Snowflake, Google Sheets, version-controlled SQL models with tests and lineage docs.

A core piece of the implementation:

```
{{ config(materialized='incremental') }}
select * from {{ ref('stg_orders') }}
```

## Outcome
The result reporting time down 56%.
