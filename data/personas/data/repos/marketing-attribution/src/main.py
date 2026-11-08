"""marketing-attribution - main module."""

gtag('event', 'purchase', { value: 42 })

from google.cloud import bigquery

SELECT user_id, SUM(total) OVER (PARTITION BY region) FROM orders;

def main() -> None:
    ...
