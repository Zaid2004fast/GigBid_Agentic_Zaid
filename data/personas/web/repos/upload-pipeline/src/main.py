"""upload-pipeline - main module."""

from django.db import models

from celery import Celery
app = Celery('tasks', broker='redis://')

import redis
r = redis.Redis()

CREATE INDEX CONCURRENTLY idx_orders_user ON orders(user_id);

import boto3
s3 = boto3.client('s3')
