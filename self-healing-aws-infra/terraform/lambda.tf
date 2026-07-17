data "archive_file" "unhealthy_remediation" {
  type        = "zip"
  source_file = "${path.module}/../lambda/remediate_unhealthy_instance.py"
  output_path = "${path.module}/build/remediate_unhealthy_instance.zip"
}

data "archive_file" "auto_recover" {
  type        = "zip"
  source_file = "${path.module}/../lambda/auto_recover_stopped_instance.py"
  output_path = "${path.module}/build/auto_recover_stopped_instance.zip"
}

resource "aws_lambda_function" "unhealthy_remediation" {
  function_name    = "${var.project_name}-remediate-unhealthy-instance"
  role             = aws_iam_role.remediation_lambda.arn
  handler          = "remediate_unhealthy_instance.handler"
  runtime          = "python3.12"
  timeout          = 30
  filename         = data.archive_file.unhealthy_remediation.output_path
  source_code_hash = data.archive_file.unhealthy_remediation.output_base64sha256

  environment {
    variables = {
      METRIC_NAMESPACE = "SelfHealingInfra"
    }
  }
}

resource "aws_lambda_function" "auto_recover" {
  function_name    = "${var.project_name}-auto-recover-stopped-instance"
  role             = aws_iam_role.remediation_lambda.arn
  handler          = "auto_recover_stopped_instance.handler"
  runtime          = "python3.12"
  timeout          = 30
  filename         = data.archive_file.auto_recover.output_path
  source_code_hash = data.archive_file.auto_recover.output_base64sha256

  environment {
    variables = {
      REMEDIATION_TAG_KEY = "SelfHealing"
      METRIC_NAMESPACE    = "SelfHealingInfra"
    }
  }
}

resource "aws_lambda_permission" "allow_sns" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.unhealthy_remediation.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.self_healing_alerts.arn
}

resource "aws_sns_topic_subscription" "lambda_remediation" {
  topic_arn = aws_sns_topic.self_healing_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.unhealthy_remediation.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auto_recover.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.instance_stopped.arn
}
