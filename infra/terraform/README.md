# infra/terraform

Production infrastructure for Ordy (doc 01 §6). **Not yet applied** — this is the
reviewed target state; a first `terraform apply` is part of the Phase 10 GA checklist.

```bash
terraform init -backend-config=backend.hcl
terraform plan  -var environment=prod
terraform apply -var environment=prod
```

Decisions worth knowing:
- **EU region by default** — GDPR data residency (doc 08 §7).
- **Per-AZ NAT gateways**, not a single shared one: an AZ outage must not take voice down.
- **Customer-managed KMS key** with rotation — it wraps the per-secret data keys used for
  restaurant credentials (doc 08 §4).
- **RDS multi-AZ + 14-day PITR** → RPO ≤ 15 min, matching the recovery objective.
- **Deletion protection on**, so a `terraform destroy` cannot take the database with it.

The Kubernetes cluster itself (EKS) and DNS/CDN are intentionally separate modules so the
data layer can be applied and reviewed independently of compute.
