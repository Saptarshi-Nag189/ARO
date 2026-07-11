output "web_url" {
  description = "ARO web UI / API"
  value       = "http://${aws_lb.main.dns_name}"
}

output "mcp_url" {
  description = "Remote MCP endpoint (claude mcp add --transport http aro <this>)"
  value       = "http://${aws_lb.main.dns_name}:8001/mcp"
}

output "ecr_repository" {
  description = "Push images here (deploy.yml does this automatically)."
  value       = aws_ecr_repository.aro.repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "reports_bucket" {
  value = aws_s3_bucket.reports.bucket
}

output "checkpoint_db_endpoint" {
  value     = aws_db_instance.checkpoints.address
  sensitive = true
}
