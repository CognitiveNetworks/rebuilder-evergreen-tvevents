variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "msk_cluster_arn" {
  description = "ARN of the MSK Kafka cluster"
  type        = string
}

variable "kafka_topic" {
  description = "Kafka topic for tvevents"
  type        = string
  default     = "tvevents"
}

variable "kafka_debug_topic" {
  description = "Kafka debug topic for tvevents"
  type        = string
  default     = "tvevents-debug"
}

variable "kafka_partitions" {
  description = "Number of Kafka partitions"
  type        = number
  default     = 12
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t4g.medium"
}

variable "redis_num_nodes" {
  description = "Number of Redis cache nodes"
  type        = number
  default     = 2
}

variable "redis_subnet_group" {
  description = "ElastiCache subnet group name"
  type        = string
}

variable "redis_security_groups" {
  description = "Security group IDs for Redis"
  type        = list(string)
}

variable "eks_oidc_provider_arn" {
  description = "ARN of the EKS OIDC provider"
  type        = string
}

variable "eks_oidc_issuer" {
  description = "OIDC issuer URL for EKS"
  type        = string
}

variable "secrets_arns" {
  description = "ARNs of Secrets Manager secrets"
  type        = list(string)
}
