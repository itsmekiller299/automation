variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "orbit"
}

variable "environment" {
  type    = string
  default = "production"
}

# --- networking ---

variable "vpc_cidr" {
  type    = string
  default = "10.60.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.60.0.0/20", "10.60.16.0/20", "10.60.32.0/20"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.60.48.0/20", "10.60.64.0/20", "10.60.80.0/20"]
}

variable "availability_zone_count" {
  type    = number
  default = 2

  validation {
    condition     = var.availability_zone_count >= 2 && var.availability_zone_count <= 3
    error_message = "Use at least 2 availability zones."
  }
}

variable "single_nat_gateway" {
  description = "One NAT gateway is cheaper but is a cross-AZ single point of failure."
  type        = bool
  default     = true
}

# --- images (set these after the ECR repositories exist) ---

variable "api_image" {
  description = "Full ECR image URI for the API/worker/beat image, including tag."
  type        = string
}

variable "dashboard_image" {
  description = "Full ECR image URI for the dashboard image, including tag."
  type        = string
}

# --- compute sizing ---

variable "api_cpu" {
  type    = number
  default = 1024
}

variable "api_memory" {
  type    = number
  default = 2048
}

variable "api_desired_count" {
  type    = number
  default = 2
}

variable "api_min_count" {
  type    = number
  default = 2
}

variable "api_max_count" {
  type    = number
  default = 6
}

variable "worker_cpu" {
  type    = number
  default = 512
}

variable "worker_memory" {
  type    = number
  default = 1024
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "worker_max_count" {
  type    = number
  default = 4
}

variable "dashboard_cpu" {
  type    = number
  default = 256
}

variable "dashboard_memory" {
  type    = number
  default = 512
}

variable "dashboard_desired_count" {
  type    = number
  default = 1
}

# --- database / cache ---

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_name" {
  type    = string
  default = "orbit"
}

variable "db_username" {
  type    = string
  default = "orbit"
}

variable "db_allocated_storage" {
  type    = number
  default = 50
}

variable "db_max_allocated_storage" {
  type    = number
  default = 200
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "db_skip_final_snapshot" {
  type    = bool
  default = false
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "redis_engine_version" {
  type    = string
  default = "7.1"
}

variable "redis_num_cache_clusters" {
  type    = number
  default = 1

  validation {
    condition     = var.redis_num_cache_clusters >= 1 && var.redis_num_cache_clusters <= 3
    error_message = "Use 1 (dev/small) or 2-3 (multi-AZ)."
  }
}

# --- TLS / public URL ---

variable "certificate_arn" {
  description = "ACM certificate ARN for the ALB. Empty serves HTTP only (not production-safe)."
  type        = string
  default     = ""
}

variable "public_base_url" {
  description = "Public https URL of the API. Empty derives it from the ALB DNS name."
  type        = string
  default     = ""
}

# --- application secrets / settings ---

variable "app_secret" {
  description = "Meta app secret used to verify X-Hub-Signature-256."
  type        = string
  sensitive   = true
}

variable "verify_token" {
  description = "Meta webhook verification token."
  type        = string
  sensitive   = true
}

variable "admin_api_key" {
  description = "Shared key for dashboard/API routes. Empty generates one in Secrets Manager."
  type        = string
  sensitive   = true
  default     = ""
}

variable "whatsapp_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "ig_page_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "orders_api_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "slack_webhook_url" {
  type      = string
  sensitive = true
  default   = ""
}

variable "smtp_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "llm_api_key" {
  description = "Anthropic API key. Empty keeps the safe template provider even when LLM_PROVIDER=anthropic."
  type        = string
  sensitive   = true
  default     = ""
}

# --- non-secret app configuration ---

variable "llm_provider" {
  type    = string
  default = "anthropic"
}

variable "llm_model" {
  type    = string
  default = "claude-sonnet-4-5"
}

variable "phone_number_id" {
  type    = string
  default = ""
}

variable "whatsapp_business_account_id" {
  type    = string
  default = ""
}

variable "ig_business_account_id" {
  type    = string
  default = ""
}

variable "whatsapp_template_name" {
  type    = string
  default = "agent_handoff"
}

variable "whatsapp_template_language" {
  type    = string
  default = "en_US"
}

variable "orders_api_url" {
  type    = string
  default = ""
}

variable "smtp_host" {
  type    = string
  default = ""
}

variable "smtp_port" {
  type    = number
  default = 587
}

variable "smtp_username" {
  type    = string
  default = ""
}

variable "smtp_from" {
  type    = string
  default = ""
}

variable "handoff_email_to" {
  type    = string
  default = ""
}

variable "data_retention_days" {
  type    = number
  default = 180
}

variable "log_retention_days" {
  type    = number
  default = 30
}
