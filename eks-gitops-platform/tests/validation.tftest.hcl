# These tests plan against a MOCKED AWS provider: no account, no credentials, nothing is created.
# They prove the input validation rejects unsafe or wrong values.

mock_provider "aws" {
  # Defaults for the data sources the modules read, so the plan can be evaluated without AWS.
  mock_data "aws_availability_zones" {
    defaults = {
      names = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
    }
  }
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
      arn        = "arn:aws:iam::123456789012:user/test"
    }
  }
  mock_data "aws_iam_session_context" {
    defaults = {
      issuer_arn = "arn:aws:iam::123456789012:role/test"
    }
  }
  mock_data "aws_partition" {
    defaults = {
      partition  = "aws"
      dns_suffix = "amazonaws.com"
    }
  }
}

run "rejects_an_endpoint_open_to_the_internet" {
  command = plan
  variables {
    kubernetes_version           = "1.33"
    endpoint_public_access_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.endpoint_public_access_cidrs]
}

run "rejects_an_empty_endpoint_allow_list" {
  command = plan
  variables {
    kubernetes_version           = "1.33"
    endpoint_public_access_cidrs = []
  }
  expect_failures = [var.endpoint_public_access_cidrs]
}

run "rejects_a_malformed_cidr" {
  command = plan
  variables {
    kubernetes_version           = "1.33"
    endpoint_public_access_cidrs = ["not-a-cidr"]
  }
  expect_failures = [var.endpoint_public_access_cidrs]
}

run "rejects_node_sizes_out_of_order" {
  command = plan
  variables {
    kubernetes_version           = "1.33"
    endpoint_public_access_cidrs = ["203.0.113.10/32"]
    node_min_size                = 3
    node_desired_size            = 2
    node_max_size                = 5
  }
  expect_failures = [var.node_max_size]
}

run "rejects_a_bad_cluster_name" {
  command = plan
  variables {
    kubernetes_version           = "1.33"
    endpoint_public_access_cidrs = ["203.0.113.10/32"]
    cluster_name                 = "Bad_Name"
  }
  expect_failures = [var.cluster_name]
}

run "rejects_a_vpc_that_is_too_small" {
  command = plan
  variables {
    kubernetes_version           = "1.33"
    endpoint_public_access_cidrs = ["203.0.113.10/32"]
    vpc_cidr                     = "10.0.0.0/24"
  }
  expect_failures = [var.vpc_cidr]
}

run "accepts_a_valid_configuration" {
  command = plan
  variables {
    kubernetes_version           = "1.33"
    endpoint_public_access_cidrs = ["203.0.113.10/32"]
  }
}

run "rejects_a_malformed_kubernetes_version" {
  command = plan
  variables {
    endpoint_public_access_cidrs = ["203.0.113.10/32"]
    kubernetes_version           = "latest"
  }
  expect_failures = [var.kubernetes_version]
}
