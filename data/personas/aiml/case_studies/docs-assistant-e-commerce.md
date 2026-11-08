---
project: docs-assistant-e-commerce
client_industry: e-commerce
date: 2026-09
type: case_study
---
# Internal knowledge assistant for a e-commerce company

## Context
Juniper E-Commerce needed a chat assistant that answers staff questions from 800 internal documents. The existing process was slow and error-prone.

## What I built
I designed and delivered a chat assistant that answers staff questions from 800 internal documents. The stack: scripting the whole backend end to end, LangChain, answers grounded in the company's own documents with citations, Qdrant, an async Python API with automatic OpenAPI docs, OpenAI.

A core piece of the implementation:

```
docs = retriever.invoke(question)
answer = llm.invoke(prompt.format(context=docs))
```

## Outcome
The result cut average search time from 5 minutes to 6 seconds.
