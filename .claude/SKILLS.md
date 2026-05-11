# Claude Skills — AUA Agent Project

## Terraform / EKS

### Provision EKS Cluster
```bash
cd infrastructure
terraform init
terraform plan
terraform apply
```
- Cluster: `capstone-eks` in `eu-central-1`
- 1 worker node: `t3.small` (keep small to save costs)
- Single NAT gateway (non-redundant)
- VPC with 2 public + 2 private subnets
- OIDC provider for IRSA (IAM Roles for Service Accounts)
- IAM roles: cluster role, node role, LB controller role

### Connect kubectl to EKS
```bash
aws eks update-kubeconfig --region eu-central-1 --name capstone-eks
```

### Install EBS CSI Driver (required for persistent volumes)
```bash
# Create IRSA role for CSI (done via Terraform OIDC provider)
aws eks create-addon --cluster-name capstone-eks \
  --addon-name aws-ebs-csi-driver \
  --service-account-role-arn arn:aws:iam::<ACCOUNT_ID>:role/capstone-eks-ebs-csi-role \
  --region eu-central-1

# Scale down to 1 replica on small nodes to save memory
kubectl scale deployment ebs-csi-controller -n kube-system --replicas=1
```

### Tear Down
```bash
cd infrastructure
terraform destroy
```

---

## Kubernetes

### Deploy the App
```bash
kubectl apply -f infrastructure/k8s/namespace.yaml
kubectl apply -f infrastructure/k8s/secrets.yaml
kubectl apply -f infrastructure/k8s/postgres.yaml
kubectl apply -f infrastructure/k8s/backend.yaml
kubectl apply -f infrastructure/k8s/frontend.yaml
```

### Update Secrets
```bash
kubectl delete secret app-secrets -n capstone
kubectl create secret generic app-secrets -n capstone \
  --from-literal=OPENAI_API_KEY='sk-...' \
  --from-literal=POSTGRES_PASSWORD='postgres'
```

### Restart After Changes
```bash
kubectl rollout restart deployment backend frontend -n capstone
kubectl rollout restart statefulset db -n capstone
```

### Get External URL
```bash
kubectl get svc frontend -n capstone -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

### Debugging
```bash
kubectl get pods -n capstone
kubectl logs <pod-name> -n capstone --tail=50
kubectl describe pod <pod-name> -n capstone
kubectl get events -n capstone --sort-by='.lastTimestamp' | tail -20
kubectl describe nodes | grep -A 8 "Allocated resources"
```

### Key Gotchas
- PostgreSQL needs `PGDATA=/var/lib/postgresql/data/pgdata` (EBS volumes have `lost+found`)
- t3.small has ~2GB RAM — keep resource requests low (100-256Mi per pod)
- CSI controller uses 240Mi x replicas — scale to 1 on small nodes
- Frontend service is `type: LoadBalancer` (AWS Classic LB, port 80 → 8501)

---

## Docker

### Build for EKS (amd64)
```bash
cd /path/to/project
docker buildx build --platform linux/amd64 -f backend/Dockerfile -t armenmadoyan/capstone-backend:latest --push .
docker buildx build --platform linux/amd64 -f frontend/Dockerfile -t armenmadoyan/capstone-frontend:latest --push .
```

### Build Locally (native arch)
```bash
docker compose up --build
```

### Key Gotchas
- Mac builds are arm64; EKS nodes are amd64 — always use `--platform linux/amd64` for EKS
- Both Dockerfiles use project root as build context: `docker build -f backend/Dockerfile .`
- Images on Docker Hub: `armenmadoyan/capstone-backend`, `armenmadoyan/capstone-frontend`

---

## GitHub Actions CI/CD

### CI (`.github/workflows/ci.yml`)
Runs on: PRs and pushes to `main`
- Lint backend + frontend with `ruff check` and `ruff format --check`
- Run pytest with pgvector service container
- Build Docker images (no push) to verify they compile

### CD (`.github/workflows/cd.yml`)
Runs on: push to `main`
- Build + push images to Docker Hub (tagged `latest` + commit SHA)
- Configure AWS credentials, update kubeconfig
- Apply k8s manifests, set new image tags, wait for rollout

### Required GitHub Secrets
| Secret                  | Value                          |
|-------------------------|--------------------------------|
| `DOCKERHUB_USERNAME`    | `armenmadoyan`                 |
| `DOCKERHUB_TOKEN`       | Docker Hub access token (R+W)  |
| `AWS_ACCESS_KEY_ID`     | AWS access key                 |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key                 |
| `OPENAI_API_KEY`        | OpenAI API key (for tests)     |

### Lint Before Committing
```bash
ruff check backend/ frontend/ && ruff format backend/ frontend/
```

---

## Git

- Primary remote: `aua` → `git@github.com:ArmenMadoyan/aua_agent.git`
- Push: `git push aua main`
- CI/CD triggers on push to `main`

---

## Common Issues & Fixes

| Problem | Cause | Fix |
|---------|-------|-----|
| Backend crashes silently | Invalid `OPENAI_API_KEY` — embeddings init at module import | Set valid key in k8s secret |
| `ImagePullBackOff` on EKS | Image built for arm64, node is amd64 | Rebuild with `--platform linux/amd64` |
| PVC stuck in Pending | EBS CSI driver missing credentials | Install CSI as EKS addon with IRSA role |
| DB pod `CrashLoopBackOff` | `lost+found` in EBS mount | Set `PGDATA` env to a subdirectory |
| Pods `Insufficient memory` | t3.small only has ~2GB | Reduce resource requests, scale CSI to 1 |
| `create_agent() got unexpected keyword argument` | Wrong parameter name | Use `prompt=` (not `instructions=`) |
| Alembic migration hangs | Wrong DB URL | Ensure `DATABASE_URL` env var is set correctly |
