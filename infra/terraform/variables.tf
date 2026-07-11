variable "project" {
  description = "Project name used as a prefix for every resource."
  type        = string
  default     = "aro"
}

variable "aws_region" {
  description = "AWS region (ap-south-1 = Mumbai, lowest latency from Chennai)."
  type        = string
  default     = "ap-south-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "web_cpu" {
  description = "Fargate CPU units for the web service (256 = 0.25 vCPU)."
  type        = number
  default     = 512
}

variable "web_memory" {
  description = "Fargate memory (MiB) for the web service."
  type        = number
  default     = 1024
}

variable "web_desired_count" {
  description = "Number of web tasks. Set 0 to pause the service (cost control)."
  type        = number
  default     = 1
}

variable "mcp_desired_count" {
  description = "Number of MCP server tasks. Set 0 to disable remote MCP."
  type        = number
  default     = 1
}

variable "db_instance_class" {
  description = "RDS instance class for the LangGraph checkpoint store."
  type        = string
  default     = "db.t4g.micro" # free-tier eligible
}

variable "db_allocated_storage" {
  description = "RDS storage in GB."
  type        = number
  default     = 20
}

variable "image_tag" {
  description = "Container image tag to deploy (deploy.yml pushes :latest and :<sha>)."
  type        = string
  default     = "latest"
}
