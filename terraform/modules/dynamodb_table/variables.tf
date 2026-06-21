variable "table_name" {
  type        = string
  description = "The name of the DynamoDB table to create"
}

variable "hash_key" {
  type        = string
  description = "The name of the hash key attribute for the DynamoDB table. Used to uniquely identify items in the table."
}

variable "attributes" {
  type = list(object({
    name = string
    type = string
  }))
  description = "A list of attributes to define for the DynamoDB table. Each attribute should have a name and a type (e.g. 'S' for string, 'N' for number)."
}

variable "stream_enabled" {
  type        = bool
  description = "Whether to enable DynamoDB Streams on the table"
  default     = false
}

variable "stream_view_type" {
  type        = string
  description = "The view type for the DynamoDB stream (e.g. NEW_IMAGE, OLD_IMAGE, NEW_AND_OLD_IMAGES, KEYS_ONLY). Required if stream_enabled is true."
  default     = null
}

variable "global_secondary_index" {
  type = object({
    name            = string
    hash_key        = string
    projection_type = string
  })
  description = <<-EOT
    An optional global secondary index to create on the DynamoDB table.
    If provided, should include:
      - name: the index name
      - hash_key: the hash key attribute
      - projection_type: ALL, KEYS_ONLY, or INCLUDE
  EOT
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to the DynamoDB table"
}
