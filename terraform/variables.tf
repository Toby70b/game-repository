variable "region" {
  description = "The AWS region to deploy resources in"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "steam_api_base_url" {
  description = "Base URL (protocol + host) for the Steam API (e.g. http://host.docker.internal:8080 for local WireMock)"
  type        = string
  default     = "https://api.steampowered.com"
}
