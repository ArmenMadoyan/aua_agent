## AUA Q&A Agent

AI-powered Q&A agent for **American University of Armenia (AUA) policies** — built with FastAPI, Streamlit, LangGraph, and OpenAI GPT-4.1.

### Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Streamlit  │────▶│   FastAPI    │────▶│  PostgreSQL 16   │
│   Frontend   │     │   Backend    │     │  + pgvector      │
│   :8501      │     │   :8000      │     │  :5432           │
└──────────────┘     └──────┬───────┘     └──────────────────┘
                            │
                     ┌──────▼───────┐
                     │  LangGraph   │
                     │  Agents      │
                     │  + OpenAI    │
                     └──────────────┘
```

### Project Structure

```
├── backend/              # FastAPI REST API
│   ├── ai/               # LangGraph agents, tools, vector store, orchestrator
│   ├── main.py           # App entrypoint
│   ├── models.py         # SQLAlchemy models
│   ├── services.py       # Business logic
│   └── Dockerfile
├── frontend/             # Streamlit web UI
│   ├── app.py
│   └── Dockerfile
├── infrastructure/       # IaC and K8s
│   ├── *.tf              # Terraform (EKS, VPC, IAM)
│   └── k8s/              # Kubernetes manifests
├── .github/workflows/    # CI/CD pipelines
├── alembic/              # Database migrations
├── aua_policy_pdfs/      # AUA policy PDFs (RAG data source)
└── docker-compose.yml    # Local Docker setup
```

---

## Running Locally

### Prerequisites
- Python 3.12+
- PostgreSQL 16 with pgvector extension
- OpenAI API key

### Option 1: Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...

docker compose up --build
```

- Frontend: http://localhost:8501
- Backend API docs: http://localhost:8000/docs

### Option 2: Manual Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env: set OPENAI_API_KEY and DATABASE_URL
# Example: DATABASE_URL=postgresql://postgres:postgres@localhost:5432/aua_agent

# Run database migrations
alembic upgrade head

# Start backend (terminal 1)
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Start frontend (terminal 2)
streamlit run frontend/app.py
```

- Frontend: http://localhost:8501
- Backend API docs: http://localhost:8000/docs

### Environment Variables

| Variable              | Required | Default | Description                        |
|-----------------------|----------|---------|------------------------------------|
| `OPENAI_API_KEY`      | Yes      | —       | OpenAI API key                     |
| `DATABASE_URL`        | Yes      | —       | PostgreSQL connection string       |
| `EMBEDDING_DIMENSION` | No       | `1536`  | Embedding vector dimension         |
| `DEFAULT_USER_ID`     | No       | `1`     | Default user ID                    |

---

## Running on AWS (EKS)

### Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform >= 1.5
- kubectl
- Docker with buildx
- Docker Hub account

### 1. Provision Infrastructure

```bash
cd infrastructure
terraform init
terraform plan
terraform apply
```

This creates:
- VPC with 2 public + 2 private subnets
- EKS cluster (`capstone-eks`) in `eu-central-1`
- Worker node group (t3.small)
- Single NAT gateway (cost-optimized, non-redundant)
- IAM roles for cluster, nodes, and load balancer controller
- OIDC provider for IRSA

### 2. Connect kubectl

```bash
aws eks update-kubeconfig --region eu-central-1 --name capstone-eks
kubectl get nodes   # Verify connection
```

### 3. Install EBS CSI Driver

Required for persistent volumes (PostgreSQL data):

```bash
# Create IAM role for CSI driver (uses OIDC/IRSA)
# Then install as EKS managed addon:
aws eks create-addon --cluster-name capstone-eks \
  --addon-name aws-ebs-csi-driver \
  --service-account-role-arn arn:aws:iam::<ACCOUNT_ID>:role/capstone-eks-ebs-csi-role \
  --region eu-central-1

# On small nodes, scale controller to 1 to save memory:
kubectl scale deployment ebs-csi-controller -n kube-system --replicas=1
```

### 4. Build and Push Docker Images

```bash
# Login to Docker Hub
docker login

# Build for amd64 (EKS node architecture) and push
docker buildx build --platform linux/amd64 -f backend/Dockerfile \
  -t <dockerhub-user>/capstone-backend:latest --push .

docker buildx build --platform linux/amd64 -f frontend/Dockerfile \
  -t <dockerhub-user>/capstone-frontend:latest --push .
```

### 5. Deploy to Kubernetes

```bash
# Create namespace and secrets
kubectl apply -f infrastructure/k8s/namespace.yaml

kubectl create secret generic app-secrets -n capstone \
  --from-literal=OPENAI_API_KEY='sk-...' \
  --from-literal=POSTGRES_PASSWORD='postgres'

# Deploy services
kubectl apply -f infrastructure/k8s/postgres.yaml
kubectl apply -f infrastructure/k8s/backend.yaml
kubectl apply -f infrastructure/k8s/frontend.yaml

# Check status
kubectl get pods -n capstone

# Get external URL
kubectl get svc frontend -n capstone \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

### 6. Kubernetes Manifest Summary

| Manifest          | Resource                                            |
|-------------------|-----------------------------------------------------|
| `namespace.yaml`  | `capstone` namespace                                |
| `secrets.yaml`    | OpenAI API key + Postgres password                  |
| `postgres.yaml`   | StatefulSet + headless Service + 5Gi PVC            |
| `backend.yaml`    | Deployment + ClusterIP Service (port 8000)          |
| `frontend.yaml`   | Deployment + LoadBalancer Service (port 80 → 8501)  |

---

## CI/CD

GitHub Actions pipelines in `.github/workflows/`:

### CI (`ci.yml`) — PRs and pushes to main
- Lint with `ruff check` and `ruff format --check`
- Run tests with pgvector service container
- Build Docker images (verify compilation)

### CD (`cd.yml`) — pushes to main
- Build and push images to Docker Hub (tagged `latest` + commit SHA)
- Deploy to EKS: apply manifests, update image tags, wait for rollout

### Required GitHub Secrets

| Secret                  | Description                    |
|-------------------------|--------------------------------|
| `DOCKERHUB_USERNAME`    | Docker Hub username            |
| `DOCKERHUB_TOKEN`       | Docker Hub access token (R+W)  |
| `AWS_ACCESS_KEY_ID`     | AWS access key                 |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key                 |
| `OPENAI_API_KEY`        | OpenAI API key (for tests)     |

---

## API Endpoints

| Method   | Endpoint              | Description                          |
|----------|-----------------------|--------------------------------------|
| `POST`   | `/chat/answer`        | Ask a question (auto-routes agent)   |
| `POST`   | `/chat/get_messages`  | List messages for a chat             |
| `DELETE` | `/chat/delete`        | Delete a chat session                |
| `GET`    | `/docs`               | Swagger UI                           |

### Tear Down

```bash
# Delete K8s resources
kubectl delete namespace capstone

# Destroy AWS infrastructure
cd infrastructure
terraform destroy
```
