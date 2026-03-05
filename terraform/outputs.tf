output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = aws_elasticache_replication_group.tvevents.primary_endpoint_address
}

output "service_role_arn" {
  description = "IAM role ARN for the tvevents service"
  value       = aws_iam_role.tvevents_service.arn
}
