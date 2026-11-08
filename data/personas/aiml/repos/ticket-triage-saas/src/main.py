"""ticket-triage-saas - main module."""

from transformers import AutoModelForSequenceClassification

from peft import LoraConfig, get_peft_model

import torch
model = torch.nn.Sequential(...)

tokens = tokenizer(texts, truncation=True)

def main() -> None:
    ...

from langchain_core.prompts import ChatPromptTemplate
