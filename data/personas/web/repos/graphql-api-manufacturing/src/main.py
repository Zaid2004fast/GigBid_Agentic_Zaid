"""graphql-api-manufacturing - main module."""

type Query { orders(userId: ID!): [Order] }

const http = require('http')

interface Order { id: string; total: number }

CREATE INDEX CONCURRENTLY idx_orders_user ON orders(user_id);
