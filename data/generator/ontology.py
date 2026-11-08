"""Skill ontology shared by the data generator, GigSim and the RAG layer.

Each skill has
  * name      - canonical display name
  * aliases   - exact strings that name the skill (what BM25 is good at)
  * implicit  - phrases that *describe* the skill without naming it
                (what defeats keyword search and tests dense retrieval / HyDE)
  * code      - a code fragment that reveals the skill (multi-vector code chunks)
  * domain    - aiml | web | data | off (off-domain, used for skip jobs)
"""
from __future__ import annotations

SKILLS: dict[str, dict] = {
    # ---------------- AI / ML ----------------
    "python": {"name": "Python", "aliases": ["Python", "python3"], "implicit": ["scripting the whole backend end to end"],
               "code": "def main() -> None:\n    ...", "domain": "aiml"},
    "pytorch": {"name": "PyTorch", "aliases": ["PyTorch", "torch"], "implicit": ["trained the network with a custom training loop on GPUs"],
                "code": "import torch\nmodel = torch.nn.Sequential(...)", "domain": "aiml"},
    "scikit-learn": {"name": "scikit-learn", "aliases": ["scikit-learn", "sklearn"], "implicit": ["gradient boosted trees with cross-validated hyper-parameters"],
                     "code": "from sklearn.ensemble import GradientBoostingClassifier", "domain": "aiml"},
    "huggingface": {"name": "Hugging Face Transformers", "aliases": ["Hugging Face", "transformers", "HF Transformers"],
                    "implicit": ["fine-tuned a pretrained encoder from the model hub"],
                    "code": "from transformers import AutoModelForSequenceClassification", "domain": "aiml"},
    "langchain": {"name": "LangChain", "aliases": ["LangChain"], "implicit": ["chained prompts, retrievers and output parsers together"],
                  "code": "from langchain_core.prompts import ChatPromptTemplate", "domain": "aiml"},
    "langgraph": {"name": "LangGraph", "aliases": ["LangGraph"], "implicit": ["a stateful graph of cooperating agents with checkpoints"],
                  "code": "from langgraph.graph import StateGraph", "domain": "aiml"},
    "rag": {"name": "RAG", "aliases": ["RAG", "retrieval-augmented generation"],
            "implicit": ["answers grounded in the company's own documents with citations"],
            "code": "docs = retriever.invoke(question)\nanswer = llm.invoke(prompt.format(context=docs))", "domain": "aiml"},
    "pinecone": {"name": "Pinecone", "aliases": ["Pinecone"], "implicit": ["a managed vector index for similarity search"],
                 "code": "from pinecone import Pinecone\nindex = Pinecone().Index('docs')", "domain": "aiml"},
    "qdrant": {"name": "Qdrant", "aliases": ["Qdrant"], "implicit": ["a self-hosted vector database with payload filters"],
               "code": "from qdrant_client import QdrantClient", "domain": "aiml"},
    "faiss": {"name": "FAISS", "aliases": ["FAISS", "faiss"], "implicit": ["approximate nearest-neighbour search over millions of embeddings in memory"],
              "code": "import faiss\nindex = faiss.IndexFlatIP(dim)", "domain": "aiml"},
    "openai-api": {"name": "OpenAI API", "aliases": ["OpenAI API", "GPT-4", "OpenAI"], "implicit": ["calling a hosted large language model with function calling"],
                   "code": "from openai import OpenAI\nclient.chat.completions.create(...)", "domain": "aiml"},
    "lora": {"name": "LoRA fine-tuning", "aliases": ["LoRA", "QLoRA", "PEFT"], "implicit": ["adapted an open-weight LLM with low-rank adapters on a single GPU"],
             "code": "from peft import LoraConfig, get_peft_model", "domain": "aiml"},
    "opencv": {"name": "OpenCV", "aliases": ["OpenCV", "cv2"], "implicit": ["image preprocessing: deskewing, thresholding and contour detection"],
               "code": "import cv2\nimg = cv2.imread(path)", "domain": "aiml"},
    "yolo": {"name": "YOLO object detection", "aliases": ["YOLO", "YOLOv8", "Ultralytics"], "implicit": ["real-time bounding-box detection on video frames"],
             "code": "from ultralytics import YOLO\nmodel = YOLO('yolov8n.pt')", "domain": "aiml"},
    "mlflow": {"name": "MLflow", "aliases": ["MLflow"], "implicit": ["experiment tracking and a model registry for reproducible training runs"],
               "code": "import mlflow\nmlflow.log_metric('auc', auc)", "domain": "aiml"},
    "nlp": {"name": "NLP", "aliases": ["NLP", "natural language processing", "text classification"],
            "implicit": ["classified free-text support tickets by intent"],
            "code": "tokens = tokenizer(texts, truncation=True)", "domain": "aiml"},
    "forecasting": {"name": "Time-series forecasting", "aliases": ["time series forecasting", "Prophet", "forecasting"],
                    "implicit": ["predicted weekly demand per store with seasonality and holidays"],
                    "code": "from prophet import Prophet", "domain": "aiml"},
    "sagemaker": {"name": "AWS SageMaker", "aliases": ["SageMaker", "AWS SageMaker"], "implicit": ["deployed the model as a managed inference endpoint on AWS"],
                  "code": "from sagemaker.pytorch import PyTorchModel", "domain": "aiml"},
    # ---------------- Web / full-stack ----------------
    "react": {"name": "React", "aliases": ["React", "React.js", "ReactJS"], "implicit": ["a component-based single-page front end with hooks"],
              "code": "import { useState } from 'react'", "domain": "web"},
    "nextjs": {"name": "Next.js", "aliases": ["Next.js", "NextJS"], "implicit": ["server-rendered pages with file-based routing for SEO"],
               "code": "export default async function Page() {}  // app/page.tsx", "domain": "web"},
    "typescript": {"name": "TypeScript", "aliases": ["TypeScript", "TS"], "implicit": ["strictly typed front-end and API contracts"],
                   "code": "interface Order { id: string; total: number }", "domain": "web"},
    "nodejs": {"name": "Node.js", "aliases": ["Node.js", "NodeJS", "Node"], "implicit": ["a JavaScript runtime on the server handling the API"],
               "code": "const http = require('http')", "domain": "web"},
    "express": {"name": "Express", "aliases": ["Express", "Express.js"], "implicit": ["REST routes with middleware for auth and validation"],
                "code": "const app = express()\napp.get('/api', handler)", "domain": "web"},
    "django": {"name": "Django", "aliases": ["Django", "Django REST Framework", "DRF"], "implicit": ["a batteries-included Python web framework with an admin panel"],
               "code": "from django.db import models", "domain": "web"},
    "fastapi": {"name": "FastAPI", "aliases": ["FastAPI"], "implicit": ["an async Python API with automatic OpenAPI docs"],
                "code": "from fastapi import FastAPI\napp = FastAPI()", "domain": "web"},
    "postgres": {"name": "PostgreSQL", "aliases": ["PostgreSQL", "Postgres"], "implicit": ["a relational database with migrations and indexes tuned for slow queries"],
                 "code": "CREATE INDEX CONCURRENTLY idx_orders_user ON orders(user_id);", "domain": "web"},
    "redis": {"name": "Redis", "aliases": ["Redis"], "implicit": ["an in-memory cache in front of the database"],
              "code": "import redis\nr = redis.Redis()", "domain": "web"},
    "celery": {"name": "Celery", "aliases": ["Celery"], "implicit": ["background workers that process uploads off the request path"],
               "code": "from celery import Celery\napp = Celery('tasks', broker='redis://')", "domain": "web"},
    "graphql": {"name": "GraphQL", "aliases": ["GraphQL", "Apollo"], "implicit": ["a typed query API where the client asks for exactly the fields it needs"],
                "code": "type Query { orders(userId: ID!): [Order] }", "domain": "web"},
    "tailwind": {"name": "Tailwind CSS", "aliases": ["Tailwind", "Tailwind CSS"], "implicit": ["utility-first styling with a design-token config"],
                 "code": "<div className=\"flex gap-4 p-6\">", "domain": "web"},
    "stripe": {"name": "Stripe payments", "aliases": ["Stripe"], "implicit": ["subscription billing with webhooks for failed payments"],
               "code": "stripe.checkout.sessions.create({ mode: 'subscription' })", "domain": "web"},
    "websockets": {"name": "WebSockets", "aliases": ["WebSockets", "Socket.IO", "WebSocket"], "implicit": ["live updates pushed to the browser without polling"],
                   "code": "const ws = new WebSocket(url)", "domain": "web"},
    "docker": {"name": "Docker", "aliases": ["Docker", "docker-compose"], "implicit": ["containerised every service so it runs the same on any machine"],
               "code": "FROM python:3.11-slim", "domain": "web"},
    "aws": {"name": "AWS", "aliases": ["AWS", "Amazon Web Services", "EC2", "S3", "Lambda"], "implicit": ["hosted on Amazon's cloud with object storage and serverless functions"],
            "code": "import boto3\ns3 = boto3.client('s3')", "domain": "web"},
    "react-native": {"name": "React Native", "aliases": ["React Native", "Expo"], "implicit": ["one codebase shipped to both iOS and Android"],
                     "code": "import { View, Text } from 'react-native'", "domain": "web"},
    # ---------------- Data analytics ----------------
    "sql": {"name": "SQL", "aliases": ["SQL"], "implicit": ["window functions and CTEs over the orders tables"],
            "code": "SELECT user_id, SUM(total) OVER (PARTITION BY region) FROM orders;", "domain": "data"},
    "dbt": {"name": "dbt", "aliases": ["dbt", "dbt Core", "data build tool"], "implicit": ["version-controlled SQL models with tests and lineage docs"],
            "code": "{{ config(materialized='incremental') }}\nselect * from {{ ref('stg_orders') }}", "domain": "data"},
    "snowflake": {"name": "Snowflake", "aliases": ["Snowflake"], "implicit": ["a cloud warehouse with separate compute warehouses per team"],
                  "code": "import snowflake.connector", "domain": "data"},
    "bigquery": {"name": "BigQuery", "aliases": ["BigQuery", "GCP BigQuery"], "implicit": ["a serverless warehouse on Google Cloud billed per query"],
                 "code": "from google.cloud import bigquery", "domain": "data"},
    "airflow": {"name": "Apache Airflow", "aliases": ["Airflow", "Apache Airflow"], "implicit": ["scheduled DAGs that load data every night with retries"],
                "code": "from airflow import DAG", "domain": "data"},
    "tableau": {"name": "Tableau", "aliases": ["Tableau"], "implicit": ["interactive executive dashboards with drill-downs"],
                "code": "-- Tableau calculated field: IF [Profit] < 0 THEN 'Loss' END", "domain": "data"},
    "powerbi": {"name": "Power BI", "aliases": ["Power BI", "PowerBI", "DAX"], "implicit": ["Microsoft dashboards with measures written in a formula language"],
                "code": "Total Sales = SUM(Sales[Amount])", "domain": "data"},
    "pandas": {"name": "pandas", "aliases": ["pandas", "Pandas"], "implicit": ["cleaned and reshaped messy spreadsheets with dataframes"],
               "code": "import pandas as pd\ndf = pd.read_csv(path)", "domain": "data"},
    "excel": {"name": "Excel", "aliases": ["Excel", "Google Sheets", "VBA"], "implicit": ["pivot tables and lookup formulas for the finance team"],
              "code": "=XLOOKUP(A2, Orders!A:A, Orders!D:D)", "domain": "data"},
    "looker": {"name": "Looker", "aliases": ["Looker", "LookML", "Looker Studio"], "implicit": ["a semantic layer so business users explore metrics themselves"],
               "code": "view: orders { measure: revenue { type: sum } }", "domain": "data"},
    "ab-testing": {"name": "A/B testing", "aliases": ["A/B testing", "experimentation", "hypothesis testing"],
                   "implicit": ["measured whether the new checkout really lifted conversion with significance tests"],
                   "code": "from scipy.stats import chi2_contingency", "domain": "data"},
    "etl": {"name": "ETL pipelines", "aliases": ["ETL", "ELT", "data pipeline"], "implicit": ["moved data from the CRM into the warehouse every hour"],
            "code": "def extract(): ...\ndef transform(df): ...\ndef load(df): ...", "domain": "data"},
    "google-analytics": {"name": "Google Analytics", "aliases": ["Google Analytics", "GA4"], "implicit": ["tracked funnel events from the marketing site"],
                         "code": "gtag('event', 'purchase', { value: 42 })", "domain": "data"},
    # ---------------- Off-domain (skip jobs) ----------------
    "wordpress": {"name": "WordPress", "aliases": ["WordPress", "WooCommerce"], "implicit": [], "code": "", "domain": "off"},
    "shopify": {"name": "Shopify", "aliases": ["Shopify", "Liquid"], "implicit": [], "code": "", "domain": "off"},
    "swift": {"name": "Swift / iOS", "aliases": ["Swift", "SwiftUI", "iOS native"], "implicit": [], "code": "", "domain": "off"},
    "unity": {"name": "Unity game development", "aliases": ["Unity", "C# Unity"], "implicit": [], "code": "", "domain": "off"},
    "logo-design": {"name": "Logo design", "aliases": ["logo design", "Illustrator", "branding"], "implicit": [], "code": "", "domain": "off"},
    "video-editing": {"name": "Video editing", "aliases": ["Premiere Pro", "video editing", "After Effects"], "implicit": [], "code": "", "domain": "off"},
    "solidity": {"name": "Solidity", "aliases": ["Solidity", "smart contracts"], "implicit": [], "code": "", "domain": "off"},
    "salesforce": {"name": "Salesforce Apex", "aliases": ["Salesforce", "Apex"], "implicit": [], "code": "", "domain": "off"},
    "seo-writing": {"name": "SEO copywriting", "aliases": ["SEO writing", "copywriting", "blog posts"], "implicit": [], "code": "", "domain": "off"},
}

INDUSTRIES = ["fintech", "healthcare", "e-commerce", "logistics", "edtech", "real estate", "legal", "SaaS", "media", "manufacturing"]


def alias_index() -> dict[str, str]:
    """lower-cased alias -> skill id, longest aliases first when matching."""
    out: dict[str, str] = {}
    for sid, s in SKILLS.items():
        for a in s["aliases"] + [s["name"]]:
            out[a.lower()] = sid
    return out


def implicit_index() -> dict[str, str]:
    out: dict[str, str] = {}
    for sid, s in SKILLS.items():
        for p in s["implicit"]:
            out[p.lower()] = sid
    return out
