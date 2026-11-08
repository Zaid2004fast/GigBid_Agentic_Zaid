"""demand-forecast - main module."""

from prophet import Prophet

def main() -> None:
    ...

import pandas as pd
df = pd.read_csv(path)

import mlflow
mlflow.log_metric('auc', auc)
