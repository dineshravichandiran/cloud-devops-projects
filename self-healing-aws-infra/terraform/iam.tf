data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "remediation_lambda" {
  name               = "${var.project_name}-remediation-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "remediation_lambda_permissions" {
  statement {
    sid = "Logging"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid = "AutoScalingRemediation"
    actions = [
      "autoscaling:SetInstanceHealth",
      "autoscaling:DescribeAutoScalingInstances",
      "autoscaling:DescribeAutoScalingGroups",
    ]
    resources = ["*"]
  }

  statement {
    sid = "Ec2Remediation"
    actions = [
      "ec2:StartInstances",
      "ec2:DescribeInstances",
      "ec2:DescribeTags",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "ResolveUnhealthyTargets"
    actions   = ["elasticloadbalancing:DescribeTargetHealth"]
    resources = ["*"]
  }

  statement {
    sid       = "MetricsAndAudit"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "remediation_lambda" {
  name   = "${var.project_name}-remediation-lambda-policy"
  role   = aws_iam_role.remediation_lambda.id
  policy = data.aws_iam_policy_document.remediation_lambda_permissions.json
}

# Instance role: lets Systems Manager run commands on the web instances (used by
# scripts/simulate_failure.sh to stop httpd). It grants nothing else.
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.project_name}-instance-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "instance_ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.project_name}-instance-profile"
  role = aws_iam_role.instance.name
}
