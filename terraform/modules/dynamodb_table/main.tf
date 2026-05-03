locals {
  gsi_list = var.global_secondary_index != null ? [var.global_secondary_index] : []
}

resource "aws_dynamodb_table" "table" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = var.hash_key

  dynamic "attribute" {
    for_each = var.attributes
    content {
      name = attribute.value.name
      type = attribute.value.type
    }
  }

  dynamic "global_secondary_index" {
    for_each = local.gsi_list
    iterator = gsi
    content {
      name            = gsi.value.name
      hash_key        = gsi.value.hash_key
      projection_type = gsi.value.projection_type
    }
  }

  tags = var.tags
}