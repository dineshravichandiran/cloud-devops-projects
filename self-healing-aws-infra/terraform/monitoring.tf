resource "aws_sns_topic" "self_healing_alerts" {
  name = "${var.project_name}-self-healing-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.self_healing_alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_notification_email
}

# ALB target group unhealthy hosts -> fan out to SNS -> Lambda replaces the instance
resource "aws_cloudwatch_metric_alarm" "unhealthy_hosts" {
  alarm_name          = "${var.project_name}-unhealthy-target-hosts"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 30
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "Triggers self-healing remediation when the ALB reports unhealthy targets"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TargetGroup  = aws_lb_target_group.app.arn_suffix
    LoadBalancer = aws_lb.app.arn_suffix
  }

  alarm_actions = [aws_sns_topic.self_healing_alerts.arn]
  ok_actions    = [aws_sns_topic.self_healing_alerts.arn]
}

# Per-instance system status check failure -> built-in EC2 auto-recover action,
# a native AWS self-healing mechanism for underlying hardware/hypervisor faults.
resource "aws_cloudwatch_metric_alarm" "status_check_failed_system" {
  alarm_name          = "${var.project_name}-status-check-failed-system"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed_System"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "Recovers the instance automatically on underlying system status check failures"
  treat_missing_data  = "notBreaching"

  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.app.name
  }

  alarm_actions = ["arn:aws:automate:${var.aws_region}:ec2:recover"]
}

# EventBridge: react to an instance unexpectedly stopping (e.g. OOM kill,
# manual mistake) and start it back up if it's tagged for self-healing.
resource "aws_cloudwatch_event_rule" "instance_stopped" {
  name        = "${var.project_name}-instance-stopped"
  description = "Detects EC2 instances entering the stopped state"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
    detail = {
      state = ["stopped"]
    }
  })
}

resource "aws_cloudwatch_event_target" "auto_recover_lambda" {
  rule      = aws_cloudwatch_event_rule.instance_stopped.name
  target_id = "auto-recover-lambda"
  arn       = aws_lambda_function.auto_recover.arn
}

resource "aws_cloudwatch_dashboard" "self_healing" {
  dashboard_name = "${var.project_name}-self-healing"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Remediation actions taken"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["SelfHealingInfra", "RemediationActionsTaken", "Action", "ReplacedUnhealthyInstance"],
            ["SelfHealingInfra", "RemediationActionsTaken", "Action", "RestartedStoppedInstance"]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ALB unhealthy host count"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "UnHealthyHostCount", "TargetGroup", aws_lb_target_group.app.arn_suffix, "LoadBalancer", aws_lb.app.arn_suffix]
          ]
        }
      }
    ]
  })
}
