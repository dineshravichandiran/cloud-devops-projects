# Interview notes: eks-gitops-platform

## 60-second pitch
"This is Terraform for a small EKS cluster built the way I'd want a production one to start: nodes in private subnets,
the API endpoint restricted to specific CIDRs, secrets encrypted with KMS, control-plane logs, and IRSA. The unsafe
mistakes are blocked by validation rather than by a note in the README: you cannot open the API to 0.0.0.0/0. I validated it
with terraform validate, a mocked-provider test suite and checkov. I have **not** applied it to an AWS account, and I say
so in the README."

## Questions to expect
1. **Why private subnets for nodes?** Nodes and pods don't need inbound internet exposure; outbound goes through NAT. Only load balancers sit in public subnets.
2. **Why restrict the public endpoint instead of making it private-only?** A private-only endpoint needs a bastion or VPN to run kubectl or Terraform. A restricted public endpoint keeps access practical for a lab while limiting who can even reach the API. For production I'd go private-only.
3. **What is IRSA?** IAM roles for service accounts: the cluster's OIDC provider lets a pod's service account assume a specific IAM role, so pods get narrow AWS permissions instead of the node's broad role.
4. **Why a customer-managed KMS key for secrets?** Envelope encryption of Kubernetes Secrets in etcd, with a key whose policy and rotation I control and whose use is audited.
5. **Single NAT vs one per zone?** A single NAT is cheaper but its zone is a single point of failure for outbound traffic. It is a variable so the trade-off is explicit.
6. **How do you test Terraform without an account?** `terraform validate` for syntax and types, and `terraform test` with a mocked provider to prove the validation rules reject bad input. It proves the code is consistent, not that AWS accepts it.
7. **What did the tests catch?** Leaving `kubernetes_version` null failed at plan time ("Invalid count argument") because the module's node-group count depended on a value unknown until apply, so I made it a required input.
8. **Why did you skip two checkov rules?** `CKV_TF_1` wants git commit hashes for module sources; I pinned exact registry versions instead and documented it. `CKV_AWS_394` is about zone sets expanding; only the first 2 or 3 zones are used.
9. **How would Argo CD bootstrap here?** Install Argo CD, apply one root Application that watches a folder of child Applications (app-of-apps), so adding a workload is a Git commit.
10. **What would you add before using it for real?** Private-only endpoint plus a VPN or bastion, a remote encrypted state backend with locking, node group hardening and Pod Security settings, cost alarms, and a real plan/apply pipeline with approvals.

## Limits (say them out loud)
Not applied; not planned against real AWS; tflint not run; cost not estimated; the Argo CD bootstrap is a described plan plus one illustrative manifest.

## "Have you used EKS?"
"Not in production: my day job is AKS and Kubernetes operations. I wrote and validated EKS Terraform to learn the AWS side,
and I haven't applied it to an account. I can explain every setting and what I'd change before running it for real."
