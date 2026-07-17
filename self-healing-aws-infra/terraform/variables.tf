variable "aws_region" {
  description = "AWS region to deploy the self-healing stack into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix applied to all resources"
  type        = string
  default     = "self-healing-app"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24"]
}

variable "instance_type" {
  description = "EC2 instance type for the Auto Scaling Group"
  type        = string
  default     = "t3.micro"
}

variable "min_size" {
  description = "Minimum number of instances in the ASG"
  type        = number
  default     = 2
}

variable "max_size" {
  description = "Maximum number of instances in the ASG"
  type        = number
  default     = 6
}

variable "desired_capacity" {
  description = "Desired number of instances in the ASG"
  type        = number
  default     = 2
}

variable "alarm_notification_email" {
  description = "Email address subscribed to self-healing / incident notifications"
  type        = string
  default     = "ops-alerts@example.com"
}

variable "unhealthy_threshold_count" {
  description = "Number of consecutive failed health checks before remediation triggers"
  type        = number
  default     = 2
}
