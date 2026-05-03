variable "topic_name" {
  type = string
  description = "The name of the SNS topic"
}

variable "tags" {
  type = map(string)
  description = "Tags to apply to the SNS topic"
}