# Project Intelligence

## Architecture
- **Backend**: FastAPI (Python 3.12) — `backend/main.py`, uvicorn on port 8000
- **Frontend**: Streamlit — `frontend/app.py`, port 8501
- **Database**: PostgreSQL 16 + pgvector
- **AI**: LangGraph react agents, OpenAI GPT-4.1, PostgresSaver checkpointing

## Key Files
- `backend/main.py` — App lifespan: DB init → alembic migrations → checkpointer → agents → vector store
- `backend/ai/agents.py` — `create_react_agent(prompt=...)` for kb and course agents
- `backend/ai/vector_store.py` — OpenAIEmbeddings init at module import (needs valid API key)
- `backend/db.py` — Async SQLAlchemy engine + sync alembic runner
- `alembic/env.py` — Reads `DATABASE_URL` from env, uses psycopg driver

## Infrastructure
- `infrastructure/*.tf` — Terraform for EKS, VPC, IAM, OIDC
- `infrastructure/k8s/` — Kubernetes manifests (namespace, secrets, postgres, backend, frontend)
- `.github/workflows/` — CI (lint/test/build) and CD (push images, deploy to EKS)

## Docker
- `backend/Dockerfile` and `frontend/Dockerfile` — both use project root as build context
- Docker Hub: `armenmadoyan/capstone-backend`, `armenmadoyan/capstone-frontend`
