variable "region" {
  description = "The AWS region to deploy resources in"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "steam_api_key" {
  description = "Steam Web API key stored in SSM Parameter Store"
  type        = string
  sensitive   = true
}
