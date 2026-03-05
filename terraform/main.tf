terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "rebuilder-evergreen-tvevents-terraform-state"
    key    = "terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# EKS Namespace
resource "kubernetes_namespace" "tvevents" {
  metadata {
    name = "tvevents-${var.environment}"
  }
}

# MSK Kafka Topic
resource "aws_msk_topic" "tvevents" {
  cluster_arn        = var.msk_cluster_arn
  topic_name         = var.kafka_topic
  num_partitions     = var.kafka_partitions
  replication_factor = 3
}

resource "aws_msk_topic" "tvevents_debug" {
  cluster_arn        = var.msk_cluster_arn
  topic_name         = var.kafka_debug_topic
  num_partitions     = var.kafka_partitions
  replication_factor = 3
}

# ElastiCache Redis
resource "aws_elasticache_replication_group" "tvevents" {
  replication_group_id       = "tvevents-${var.environment}"
  description                = "Redis cache for tvevents blacklist"
  node_type                  = var.redis_node_type
  num_cache_clusters         = var.redis_num_nodes
  engine_version             = "7.1"
  port                       = 6379
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = var.redis_num_nodes > 1

  subnet_group_name  = var.redis_subnet_group
  security_group_ids = var.redis_security_groups
}

# IAM Role for EKS Service Account
resource "aws_iam_role" "tvevents_service" {
  name = "tvevents-${var.environment}-service"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.eks_oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.eks_oidc_issuer}:sub" = "system:serviceaccount:tvevents-${var.environment}:tvevents-api"
        }
      }
    }]
  })
}

# Secrets Manager access
resource "aws_iam_role_policy" "secrets_access" {
  name = "tvevents-secrets-access"
  role = aws_iam_role.tvevents_service.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = var.secrets_arns
    }]
  })
}

# MSK producer access
resource "aws_iam_role_policy" "kafka_access" {
  name = "tvevents-kafka-access"
  role = aws_iam_role.tvevents_service.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "kafka-cluster:Connect",
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData"
      ]
      Resource = "*"
    }]
  })
}
