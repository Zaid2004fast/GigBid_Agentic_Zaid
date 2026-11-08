---
project: rag-eval-media
client_industry: media
date: 2025-08
type: case_study
---
# Evaluation harness for an LLM chatbot (media)

## Context
Corvid Media needed an offline evaluation set and metrics for answer faithfulness. The existing process was slow and error-prone.

## What I built
I designed and delivered an offline evaluation set and metrics for answer faithfulness. The stack: python3, RAG, chained prompts, retrievers and output parsers together, cleaned and reshaped messy spreadsheets with dataframes.

A core piece of the implementation:

```
docs = retriever.invoke(question)
answer = llm.invoke(prompt.format(context=docs))
```

## Outcome
The result caught 76% of regressions before release.
