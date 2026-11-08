"""docs-assistant - main module."""

def main() -> None:
    ...

from langchain_core.prompts import ChatPromptTemplate

docs = retriever.invoke(question)
answer = llm.invoke(prompt.format(context=docs))

from qdrant_client import QdrantClient

from fastapi import FastAPI
app = FastAPI()

from openai import OpenAI
client.chat.completions.create(...)

FROM python:3.11-slim
