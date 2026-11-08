---
project: shelf-vision-healthcare
client_industry: healthcare
date: 2024-08
type: case_study
---
# Real-time shelf monitoring with computer vision for healthcare retail

## Context
Mosaic Healthcare needed a detector that flags empty shelves from store cameras. The existing process was slow and error-prone.

## What I built
I designed and delivered a detector that flags empty shelves from store cameras. The stack: real-time bounding-box detection on video frames, image preprocessing: deskewing, thresholding and contour detection, torch, Docker.

A core piece of the implementation:

```
import torch
model = torch.nn.Sequential(...)
```

## Outcome
The result 40% detection mAP at 4 frames per second.
