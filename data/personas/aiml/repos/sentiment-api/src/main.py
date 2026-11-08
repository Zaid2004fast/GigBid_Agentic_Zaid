"""sentiment-api - main module."""

tokens = tokenizer(texts, truncation=True)

from transformers import AutoModelForSequenceClassification

from fastapi import FastAPI
app = FastAPI()

FROM python:3.11-slim

docs = retriever.invoke(question)
answer = llm.invoke(prompt.format(context=docs))
