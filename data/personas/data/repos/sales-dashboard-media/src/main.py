"""sales-dashboard-media - main module."""

-- Tableau calculated field: IF [Profit] < 0 THEN 'Loss' END

SELECT user_id, SUM(total) OVER (PARTITION BY region) FROM orders;

import snowflake.connector

=XLOOKUP(A2, Orders!A:A, Orders!D:D)

{{ config(materialized='incremental') }}
select * from {{ ref('stg_orders') }}
