---
project: upload-pipeline
client_industry: legal
date: 2026-01
type: case_study
---
# Media upload and processing backend for a legal startup

## Context
Northwind Legal needed an upload service with background processing and S3 storage. The existing process was slow and error-prone.

## What I built
I designed and delivered an upload service with background processing and S3 storage. The stack: a batteries-included Python web framework with an admin panel, background workers that process uploads off the request path, Redis, PostgreSQL, hosted on Amazon's cloud with object storage and serverless functions.

## Outcome
The result p95 upload latency down to 6 seconds.
