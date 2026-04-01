terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

variable "cloudflare_api_token" {
  type        = string
  description = "Cloudflare API Token"
  sensitive   = true
}

variable "zone_id" {
  type        = string
  description = "Cloudflare Zone ID"
}

# 1. Rate Limiting Rule for API Endpoints
resource "cloudflare_ruleset" "api_rate_limit" {
  zone_id     = var.zone_id
  name        = "API Rate Limiting"
  description = "Rate limit API requests to prevent abuse"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action = "block"
    expression = "(http.request.uri.path matches \"^/api/\")"
    description = "Block requests exceeding 100 per minute per IP"
    enabled = true
    action_parameters {
      response {
        status_code = 429
        content = "Too Many Requests"
        content_type = "text/plain"
      }
    }
    ratelimit {
      characteristics = ["ip.src"]
      period = 60
      requests_per_period = 100
      mitigation_timeout = 600
    }
  }
}

# 2. Bot Management Rule
resource "cloudflare_ruleset" "bot_management" {
  zone_id     = var.zone_id
  name        = "Bot Management"
  description = "Block malicious bots"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action = "managed_challenge"
    expression = "(cf.bot_management.score < 30)"
    description = "Challenge requests with low bot score"
    enabled = true
  }
}

# 3. Block Known Malicious IPs
resource "cloudflare_ruleset" "block_malicious_ips" {
  zone_id     = var.zone_id
  name        = "Block Malicious IPs"
  description = "Block requests from known malicious IPs"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules {
    action = "block"
    expression = "(ip.src in $malicious_ips)"
    description = "Block requests from malicious IPs"
    enabled = true
  }
}
