terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.50" }
  }
}

variable "table_name" { type = string }
variable "common_tags" {
  type = map(string)
  default = {}
}

resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"

  # Composite key. This table stores a stream of events per shipment, not one
  # row per shipment: keying on order_id alone meant each new event silently
  # overwrote the previous one, so a shipment's history collapsed to whatever
  # arrived last. The sort key preserves the sequence and makes "all events
  # for this shipment, in order" a single query.
  range_key = "event_ts"

  tags = var.common_tags

  attribute {
    name = "order_id"
    type = "S"
  }
  attribute {
    name = "event_ts"
    type = "S"
  }
  attribute {
    name = "customer_id"
    type = "S"
  }
  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "customer-index"
    hash_key        = "customer_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

output "table_arn" { value = aws_dynamodb_table.this.arn }
