###############################################################################
# Kinesis ingestion stream.
#
# This is what makes SupplyNet structurally different from the other agent
# projects here. Elsewhere a request arrives at API Gateway and one Lambda
# answers it. Here telemetry arrives continuously and unbidden -- carrier
# scans, port feeds, IoT position pings -- and the pipeline has to decide
# which of it matters.
#
# Two properties drive the design:
#
#   Most events are uneventful. Ingest and Disruption run per record on the
#   cheap model tier; only a disruption above the severity threshold
#   escalates to Reroute and Notify. Cost tracks signal, not volume.
#
#   Order matters per shipment. A "delivered" arriving before the "out for
#   delivery" that preceded it produces nonsense, so the partition key is the
#   shipment id: Kinesis guarantees per-shard ordering, and one shipment's
#   events always land on the same shard.
#
# On-demand capacity rather than provisioned shards: this is a portfolio
# workload with bursty, low average volume, and provisioned shards bill
# hourly whether or not anything is flowing.
###############################################################################

terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.50" }
  }
}

variable "name_prefix" { type = string }
variable "processor_lambda_arn" { type = string }
variable "processor_function_name" { type = string }
variable "retention_hours" {
  type    = number
  default = 24
}
variable "batch_size" {
  type    = number
  default = 10
}
variable "common_tags" {
  type    = map(string)
  default = {}
}

resource "aws_kinesis_stream" "events" {
  name             = "${var.name_prefix}-events"
  retention_period = var.retention_hours

  stream_mode_details {
    stream_mode = "ON_DEMAND"
  }

  tags = var.common_tags
}

# Failed batches go here rather than being retried forever. Without a
# destination, a single poison record blocks its shard until the record ages
# out of the stream -- which with a 24 hour retention means a full day of
# that shipment's events going nowhere.
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-events-dlq"
  message_retention_seconds = 1209600 # 14 days
  tags                      = var.common_tags
}

resource "aws_lambda_event_source_mapping" "events" {
  event_source_arn  = aws_kinesis_stream.events.arn
  function_name     = var.processor_lambda_arn
  starting_position = "LATEST"

  batch_size                         = var.batch_size
  maximum_batching_window_in_seconds = 5

  # A record that cannot be processed is dropped after a bounded number of
  # attempts and reported, rather than stalling the shard behind it.
  maximum_retry_attempts         = 3
  bisect_batch_on_function_error = true

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.dlq.arn
    }
  }

  function_response_types = ["ReportBatchItemFailures"]
}

output "stream_name" { value = aws_kinesis_stream.events.name }
output "stream_arn" { value = aws_kinesis_stream.events.arn }
output "dlq_url" { value = aws_sqs_queue.dlq.url }
output "dlq_arn" { value = aws_sqs_queue.dlq.arn }
