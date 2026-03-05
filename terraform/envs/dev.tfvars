environment      = "dev"
kafka_partitions = 6
redis_node_type  = "cache.t4g.micro"
redis_num_nodes  = 1
# Sensitive values come from CI environment variables, not tfvars
# msk_cluster_arn, redis_subnet_group, redis_security_groups, eks_oidc_*, secrets_arns
