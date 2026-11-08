### RAG variants (dev set, all personas)

| Variant | Evidence Recall@5 | MRR | nDCG@10 | Unsupported claims / proposal (before -> after verify) | Judge score | GigSim reply rate | p95 latency (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|---|
| V0 | 0.001 | 0.004 | 0.001 | 1.846 -> 0.000 | see calibration | 0.513 | 27.939 | 0.0000 |
| V0e | 0.579 | 0.715 | 0.434 | n/a | n/a | n/a | 0.002 | n/a |
| V1 | 0.636 | 0.758 | 0.489 | n/a | n/a | n/a | 0.002 | n/a |
| V2 | 0.714 | 0.826 | 0.543 | 0.051 -> 0.000 | see calibration | 0.718 | 30.610 | 0.0000 |
| V3 | 0.712 | 0.813 | 0.538 | n/a | n/a | n/a | 5.448 | n/a |
| V4 | 0.716 | 0.831 | 0.543 | n/a | n/a | n/a | 0.038 | n/a |
| V5 | 0.743 | 0.826 | 0.558 | n/a | n/a | n/a | 0.018 | n/a |
| V6 | 0.684 | 0.816 | 0.548 | n/a | n/a | n/a | 0.015 | n/a |
| V7 | 0.602 | 0.746 | 0.446 | n/a | n/a | n/a | 0.524 | n/a |
| V9 | 0.926 | 0.970 | 0.783 | n/a | n/a | n/a | 0.030 | n/a |
| C1 | 0.744 | 0.841 | 0.558 | 0.051 -> 0.000 | see calibration | 0.684 | 35.882 | 0.0000 |
| C2 | 0.677 | 0.843 | 0.524 | n/a | n/a | n/a | 0.135 | n/a |
| C3 | 0.679 | 0.845 | 0.526 | n/a | n/a | n/a | 0.360 | n/a |
| best | 0.949 | 0.965 | 0.830 | 0.051 -> 0.000 | see calibration | 0.711 | 33.520 | 0.0000 |

### Shipped configuration (decision + proposal + outcome)

| Metric | Value |
|---|---|
| Bid-or-skip F1 | 0.831 |
| Scam precision / recall | 1.000 / 0.911 |
| Price inside fair band | 0.842 |
| Unsupported claims / proposal (before -> after) | 0.016 -> 0.000 |
| Critic send-back rate | 0.000 |
| GigSim reply / hire rate | 0.660 / 0.486 |
| p50 / p95 latency per job analysed (s) | 10.235 / 26.301 |
| p50 / p95 latency per proposal (s) | 27.568 / 38.991 |
| USD per job / per proposal | 0.0000 / 0.0000 |
| Injection posts detected | 65 of 65 (0 false alarms) |

### Multi-agent comparison (R&D question C)

| System | Bid/skip accuracy | Scams bid on | Unsupported claims / proposal | Compliance violations sent | GigSim reply rate | Tokens / job | p95 latency (s) |
|---|---|---|---|---|---|---|---|
| (a) single ReAct agent | 0.583 | 4 | 0.364 | 0 | 0.364 | 4528.9 | 140.45 |
| (b) prebuilt supervisor | 0.458 | 1 | 0.000 | 0 | 0.000 | 1462.5 | 105.95 |
| (c) GigBid graph | 0.875 | 0 | 0.000 | 0 | 0.818 | 0.0 | 10.04 |

### Other experiments

| Tool surface | Selection accuracy | Argument accuracy | Tokens / task |

|---|---|---|---|

| fine | 0.875 | 0.875 | 2250.3 |

| coarse | 0.000 | 0.000 | 486.5 |

| best | 0.950 | 0.950 | 579.7 |

| coarse_flat | 0.000 | 0.000 | 695.4 |



Prompt-injection attack success rate: naive pipeline 1.000 -> GigBid 0.000 (n=30, qwen3:1.7b).

X2 A/B: reply rate evidence_first 0.690 vs question_first 0.736, McNemar p=0.608, P(B>A)=0.742 (87 paired jobs).

Claims (naive writer): unsupported per proposal 0.483 before -> 0.000 after verification.

Claims (shipped writer): unsupported per proposal 0.000 before -> 0.000 after verification.
