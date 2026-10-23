data "aws_availability_zones" "available" {
  # checkov:skip=CKV_AWS_394: only the first az_count (2 or 3) zones are used, so a newly added zone cannot silently widen the footprint. Accepted risk.
  state = "available"

  # Only regular zones: excludes Local Zones and Wavelength zones, which are not wanted here.
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  azs             = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]      # large: nodes and pods
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 48)] # small: load balancers and NAT
}

module "vpc" {
  # checkov:skip=CKV_TF_1: registry module pinned to an exact version; a commit hash would need a git source. Accepted risk, see README.
  source  = "terraform-aws-modules/vpc/aws"
  version = "6.7.3"

  name = var.cluster_name
  cidr = var.vpc_cidr
  azs  = local.azs

  private_subnets = local.private_subnets
  public_subnets  = local.public_subnets

  # Nodes live in private subnets and reach the internet through NAT.
  enable_nat_gateway     = true
  single_nat_gateway     = var.single_nat_gateway
  one_nat_gateway_per_az = !var.single_nat_gateway

  enable_dns_hostnames = true
  enable_dns_support   = true

  # Tags the AWS load balancer controller looks for.
  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

module "eks" {
  # checkov:skip=CKV_TF_1: registry module pinned to an exact version; a commit hash would need a git source. Accepted risk, see README.
  source  = "terraform-aws-modules/eks/aws"
  version = "21.29.0"

  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # API endpoint: reachable privately from the VPC, and publicly ONLY from the CIDRs you list.
  endpoint_private_access      = true
  endpoint_public_access       = true
  endpoint_public_access_cidrs = var.endpoint_public_access_cidrs

  # IAM roles for service accounts (the OIDC provider), for things like the load balancer controller.
  enable_irsa = true

  # Control-plane logs, kept for a limited time.
  enabled_log_types                      = var.enabled_log_types
  create_cloudwatch_log_group            = true
  cloudwatch_log_group_retention_in_days = var.log_retention_days

  # Kubernetes Secrets are encrypted with a customer-managed KMS key.
  create_kms_key    = true
  encryption_config = { resources = ["secrets"] }

  # The identity that runs Terraform gets cluster admin through an access entry (no aws-auth ConfigMap).
  enable_cluster_creator_admin_permissions = true

  addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.node_instance_types
      min_size       = var.node_min_size
      desired_size   = var.node_desired_size
      max_size       = var.node_max_size
    }
  }
}
