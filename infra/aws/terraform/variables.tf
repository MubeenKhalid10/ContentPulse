variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "contentpulse"
}

variable "environment" {
  description = "Environment name, e.g. prod or staging."
  type        = string
  default     = "prod"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

# --- HTTPS ------------------------------------------------------------------------

variable "domain_name" {
  description = "Public hostname, e.g. app.example.com. Empty: use the load balancer DNS name over HTTP."
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate for domain_name, in the same region. Empty: HTTP only (for testing; session cookies are then not marked Secure)."
  type        = string
  default     = ""
}

# --- Application ------------------------------------------------------------------

variable "image_tag" {
  description = "Image tag the services run. deploy.sh pushes a commit tag and this one."
  type        = string
  default     = "latest"
}

variable "auth_provider" {
  description = "local, or supabase (then set SUPABASE_URL and SUPABASE_ANON_KEY in the app secret)."
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local", "supabase"], var.auth_provider)
    error_message = "auth_provider must be local or supabase."
  }
}

variable "llm_provider" {
  description = "gemini, anthropic or none. The key goes in the app secret as LLM_API_KEY."
  type        = string
  default     = "gemini"

  validation {
    condition     = contains(["gemini", "anthropic", "none"], var.llm_provider)
    error_message = "llm_provider must be gemini, anthropic or none."
  }
}

# --- Sizing -----------------------------------------------------------------------

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "protect_data" {
  description = "Deletion protection plus a final snapshot for the database, and keep the creatives bucket on destroy."
  type        = bool
  default     = true
}

variable "services" {
  description = "CPU units, memory (MiB) and task count per service. Keep beat at 1."
  type = map(object({
    cpu    = number
    memory = number
    count  = number
  }))
  default = {
    api    = { cpu = 512, memory = 1024, count = 1 }
    worker = { cpu = 512, memory = 1024, count = 1 }
    beat   = { cpu = 256, memory = 512, count = 1 }
    web    = { cpu = 256, memory = 512, count = 1 }
  }

  validation {
    condition     = var.services["beat"].count <= 1
    error_message = "Run at most one beat task, or scheduled jobs fire twice."
  }
}
