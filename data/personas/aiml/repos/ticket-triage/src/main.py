"""ticket-triage - main module."""

from transformers import AutoModelForSequenceClassification

from peft import LoraConfig, get_peft_model

import torch
model = torch.nn.Sequential(...)

tokens = tokenizer(texts, truncation=True)

def main() -> None:
    ...

from qdrant_client import QdrantClient
