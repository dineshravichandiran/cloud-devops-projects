variable "region" {
  description = "AWS region for the cluster."
  type        = string
  default     = "ap-south-1"
}

variable "cluster_name" {
  description = "EKS cluster name (also used as a prefix for the VPC)."
  type        = string
  default     = "gitops-lab"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,38}[a-z0-9]$", var.cluster_name))
    error_message = "cluster_name must be 4 to 40 characters: lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "kubernetes_version" {
  description = "Kubernetes minor version, e.g. \"1.33\". Required: with null, the EKS module cannot size its node groups at plan time (\"Invalid count argument\"). Pick a version EKS currently supports (check the AWS docs)."
  type        = string

  validation {
    condition     = can(regex("^1\\.[0-9]{2}$", var.kubernetes_version))
    error_message = "kubernetes_version must look like \"1.33\"."
  }
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && tonumber(split("/", var.vpc_cidr)[1]) <= 20
    error_message = "vpc_cidr must be a valid CIDR no smaller than a /20 (the subnets are carved out of it)."
  }
}

variable "az_count" {
  description = "How many availability zones to spread subnets and nodes across."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3."
  }
}

variable "single_nat_gateway" {
  description = "true = one shared NAT gateway (cheaper, but one AZ is a single point of failure for outbound traffic). false = one per AZ."
  type        = bool
  default     = true
}

variable "endpoint_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public Kubernetes API endpoint. Deliberately has NO default and cannot contain 0.0.0.0/0."
  type        = list(string)

  validation {
    condition     = length(var.endpoint_public_access_cidrs) > 0 && alltrue([for c in var.endpoint_public_access_cidrs : can(cidrhost(c, 0))])
    error_message = "Provide at least one valid CIDR, for example your office or home IP as x.x.x.x/32."
  }

  validation {
    condition     = !contains(var.endpoint_public_access_cidrs, "0.0.0.0/0") && !contains(var.endpoint_public_access_cidrs, "::/0")
    error_message = "The Kubernetes API must not be open to the whole internet. Use specific CIDRs."
  }
}

variable "enabled_log_types" {
  description = "Control-plane log types sent to CloudWatch."
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  validation {
    condition     = alltrue([for t in var.enabled_log_types : contains(["api", "audit", "authenticator", "controllerManager", "scheduler"], t)])
    error_message = "Valid log types: api, audit, authenticator, controllerManager, scheduler."
  }
}

variable "log_retention_days" {
  description = "How long control-plane logs are kept."
  type        = number
  default     = 30
}

variable "node_instance_types" {
  description = "Instance types for the managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_min_size" {
  type    = number
  default = 1
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 3

  validation {
    condition     = var.node_max_size >= var.node_desired_size && var.node_desired_size >= var.node_min_size && var.node_min_size >= 1
    error_message = "Sizes must satisfy 1 <= node_min_size <= node_desired_size <= node_max_size."
  }
}

variable "tags" {
  description = "Tags applied to everything the provider creates."
  type        = map(string)
  default = {
    Project   = "eks-gitops-platform"
    ManagedBy = "terraform"
  }
}
