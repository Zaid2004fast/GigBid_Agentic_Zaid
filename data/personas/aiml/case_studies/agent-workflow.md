---
project: agent-workflow
client_industry: real estate
date: 2024-08
type: case_study
---
# Multi-agent document review workflow for a real estate team

## Context
Kestrel Real Estate needed agents that review contracts and flag risky clauses with human approval. The existing process was slow and error-prone.

## What I built
I designed and delivered agents that review contracts and flag risky clauses with human approval. The stack: a stateful graph of cooperating agents with checkpoints, scripting the whole backend end to end, calling a hosted large language model with function calling, an async Python API with automatic OpenAPI docs, answers grounded in the company's own documents with citations, image preprocessing: deskewing, thresholding and contour detection.

A core piece of the implementation:

```
from langgraph.graph import StateGraph
```

## Outcome
The result review time down 90%.
