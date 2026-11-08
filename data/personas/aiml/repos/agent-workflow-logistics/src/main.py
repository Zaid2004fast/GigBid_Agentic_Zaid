"""agent-workflow-logistics - main module."""

from langgraph.graph import StateGraph

def main() -> None:
    ...

from openai import OpenAI
client.chat.completions.create(...)

from fastapi import FastAPI
app = FastAPI()

docs = retriever.invoke(question)
answer = llm.invoke(prompt.format(context=docs))

import pandas as pd
df = pd.read_csv(path)
