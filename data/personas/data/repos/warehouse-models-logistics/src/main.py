"""warehouse-models-logistics - main module."""

{{ config(materialized='incremental') }}
select * from {{ ref('stg_orders') }}

import snowflake.connector

SELECT user_id, SUM(total) OVER (PARTITION BY region) FROM orders;

from airflow import DAG
