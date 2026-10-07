output "app_url" {
  description = "Open this in a browser once deploy.sh has finished."
  value       = local.app_url
}

output "load_balancer_dns" {
  description = "Point your domain's CNAME (or Route 53 alias) here."
  value       = aws_lb.main.dns_name
}

output "region" {
  value = var.region
}

output "cluster" {
  value = aws_ecs_cluster.main.name
}

output "api_repository" {
  value = aws_ecr_repository.repo["api"].repository_url
}

output "web_repository" {
  value = aws_ecr_repository.repo["web"].repository_url
}

output "image_tag" {
  value = var.image_tag
}

output "migrate_task_definition" {
  value = aws_ecs_task_definition.migrate.family
}

output "private_subnets" {
  value = join(",", aws_subnet.private[*].id)
}

output "app_security_group" {
  value = aws_security_group.app.id
}

output "app_secret_arn" {
  description = "Put LLM_API_KEY and other optional keys in this secret."
  value       = aws_secretsmanager_secret.app.arn
}

output "creatives_bucket" {
  value = aws_s3_bucket.creatives.bucket
}

output "log_group" {
  value = aws_cloudwatch_log_group.app.name
}
