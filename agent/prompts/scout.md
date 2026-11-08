---
version: scout-v1
node: Scout
model_route: none
---
## system
(Not sent to a model.) The Scout runs saved searches through the marketplace port on a schedule,
deduplicates by job id and by a normalised content fingerprint (reposts), and queues new jobs.

## user
{search}