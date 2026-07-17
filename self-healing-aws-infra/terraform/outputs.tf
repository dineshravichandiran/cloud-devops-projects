output "alb_dns_name" {
  description = "Public DNS name of the load balancer fronting the self-healing app"
  value       = aws_lb.app.dns_name
}

output "autoscaling_group_name" {
  description = "Name of the self-healing Auto Scaling Group"
  value       = aws_autoscaling_group.app.name
}

output "sns_alert_topic_arn" {
  description = "SNS topic ARN that fans out remediation alerts"
  value       = aws_sns_topic.self_healing_alerts.arn
}

output "dashboard_url" {
  description = "CloudWatch dashboard showing remediation activity"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.self_healing.dashboard_name}"
}
