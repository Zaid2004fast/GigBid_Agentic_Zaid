"""ab-test-review - main module."""

from scipy.stats import chi2_contingency

def main() -> None:
    ...

import pandas as pd
df = pd.read_csv(path)

SELECT user_id, SUM(total) OVER (PARTITION BY region) FROM orders;
