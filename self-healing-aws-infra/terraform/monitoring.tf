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
  # The ALB publishes this metric once a minute. A 30 second period leaves every other period
  # empty, and with treat_missing_data = "notBreaching" that resets the count, so the alarm
  # could never see two breaching periods in a row. Keep this a multiple of 60.
  period             = 60
  statistic          = "Maximum"
  threshold          = 1
  alarm_description  = "Triggers self-healing remediation when the ALB reports unhealthy targets"
  treat_missing_data = "notBreaching"

  dimensions = {
    TargetGroup  = aws_lb_target_group.app.arn_suffix
    LoadBalancer = aws_lb.app.arn_suffix
  }

  alarm_actions = [aws_sns_topic.self_healing_alerts.arn]
  ok_actions    = [aws_sns_topic.self_healing_alerts.arn]
}

# Note: the native EC2 auto-recover alarm (StatusCheckFailed_System -> ec2:recover) is not
# part of this stack. That action only works on an alarm for one specific instance
# (InstanceId dimension), and ASG members are created and replaced dynamically, so it
# cannot be declared here. A failed host is covered by the ELB health check instead:
# the ASG replaces the instance.

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
            ["SelfHealingInfra", "RemediationActionsTaken", "Action", "ReplacedUnhealthyInstance", { "stat" = "Sum" }],
            ["SelfHealingInfra", "RemediationActionsTaken", "Action", "RestartedStoppedInstance", { "stat" = "Sum" }]
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
