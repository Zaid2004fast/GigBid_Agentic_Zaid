---
project: sentiment-api-healthcare
client_industry: healthcare
date: 2026-01
type: case_study
---
# Review sentiment API for a healthcare brand

## Context
Atlas Healthcare needed an API that scores customer reviews and extracts complaint themes. The existing process was slow and error-prone.

## What I built
I designed and delivered an API that scores customer reviews and extracts complaint themes. The stack: NLP, transformers, FastAPI, containerised every service so it runs the same on any machine.

A core piece of the implementation:

```
from transformers import AutoModelForSequenceClassification
```

## Outcome
The result processes 20000 reviews per day.
