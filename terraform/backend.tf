terraform {
  backend "s3" {
    bucket       = "terraform-state-8318925"
    key          = "terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
