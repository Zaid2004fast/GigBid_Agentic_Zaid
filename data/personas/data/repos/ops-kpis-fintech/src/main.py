"""ops-kpis-fintech - main module."""

Total Sales = SUM(Sales[Amount])

SELECT user_id, SUM(total) OVER (PARTITION BY region) FROM orders;

=XLOOKUP(A2, Orders!A:A, Orders!D:D)

import pandas as pd
df = pd.read_csv(path)
