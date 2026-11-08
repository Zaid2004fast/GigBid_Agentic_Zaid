"""rag-eval-media - main module."""

def main() -> None:
    ...

docs = retriever.invoke(question)
answer = llm.invoke(prompt.format(context=docs))

from langchain_core.prompts import ChatPromptTemplate

import pandas as pd
df = pd.read_csv(path)
