---
project: ticket-triage-saas
client_industry: SaaS
date: 2023-12
type: case_study
---
# Support ticket triage with a fine-tuned language model (SaaS)

## Context
Lumen Saas needed a fine-tuned classifier that routes tickets to the right queue. The existing process was slow and error-prone.

## What I built
I designed and delivered a fine-tuned classifier that routes tickets to the right queue. The stack: fine-tuned a pretrained encoder from the model hub, adapted an open-weight LLM with low-rank adapters on a single GPU, PyTorch, text classification, scripting the whole backend end to end, chained prompts, retrievers and output parsers together.

A core piece of the implementation:

```
from langchain_core.prompts import ChatPromptTemplate
```

## Outcome
The result routing accuracy of 43% on 800 tickets.
