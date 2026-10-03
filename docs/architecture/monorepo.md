# Monorepo Architecture

## Runtime

elder-app -> backend -> PostgreSQL / Redis
writer-admin -> backend
backend -> ai-service
ai-service -> LLM / RAG / Embedding

## Source

templates/ = generation source
apps/ = product applications
services/ = independent services
packages/ = shared code
infra/ = deployment
docs/ = knowledge
