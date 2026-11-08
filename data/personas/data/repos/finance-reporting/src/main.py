"""finance-reporting - main module."""

=XLOOKUP(A2, Orders!A:A, Orders!D:D)

Total Sales = SUM(Sales[Amount])

SELECT user_id, SUM(total) OVER (PARTITION BY region) FROM orders;

def extract(): ...
def transform(df): ...
def load(df): ...
