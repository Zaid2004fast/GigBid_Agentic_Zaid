---
project: upload-pipeline-logistics
client_industry: logistics
date: 2023-02
type: case_study
---
# Media upload and processing backend for a logistics startup

## Context
Juniper Logistics needed an upload service with background processing and S3 storage. The existing process was slow and error-prone.

## What I built
I designed and delivered an upload service with background processing and S3 storage. The stack: Django REST Framework, Celery, an in-memory cache in front of the database, PostgreSQL, EC2.

A core piece of the implementation:

```
from django.db import models
```

## Outcome
The result p95 upload latency down to 3 seconds.
