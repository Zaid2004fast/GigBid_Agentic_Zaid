---
project: realtime-chat-real-estate
client_industry: real estate
date: 2026-07
type: case_study
---
# Real-time support chat for a real estate platform

## Context
Pioneer Real Estate needed live chat with typing indicators and presence. The existing process was slow and error-prone.

## What I built
I designed and delivered live chat with typing indicators and presence. The stack: Socket.IO, a JavaScript runtime on the server handling the API, an in-memory cache in front of the database, ReactJS, FastAPI.

A core piece of the implementation:

```
const http = require('http')
```

## Outcome
The result handles 150000 concurrent users.
