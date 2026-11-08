---
project: rag-eval
client_industry: legal
date: 2025-06
type: case_study
---
# Evaluation harness for an LLM chatbot (legal)

## Context
Driftwood Legal needed an offline evaluation set and metrics for answer faithfulness. The existing process was slow and error-prone.

## What I built
I designed and delivered an offline evaluation set and metrics for answer faithfulness. The stack: Python, answers grounded in the company's own documents with citations, LangChain, cleaned and reshaped messy spreadsheets with dataframes, QLoRA.

A core piece of the implementation:

```
def main() -> None:
    ...
```

## Outcome
The result caught 59% of regressions before release.
