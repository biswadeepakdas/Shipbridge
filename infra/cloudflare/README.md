# ShipBridge Cloudflare WAF Configuration

## Prerequisites
- Cloudflare account with Pro or Business plan (WAF requires paid plan)
- Zone configured for the ShipBridge domain
- `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ZONE_ID` environment variables

## Deployment Steps

### 1. Set environment variables
```bash
export CLOUDFLARE_API_TOKEN="your-api-token"
export CLOUDFLARE_ZONE_ID="your-zone-id"
```

### 2. Apply WAF custom rules
```bash
curl -X PUT "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @waf-rules.json
```

### 3. Enable managed rulesets
Via the Cloudflare dashboard:
- Security > WAF > Managed rules
- Enable "Cloudflare Managed Ruleset"
- Enable "OWASP ModSecurity Core Rule Set"

### 4. Verify
Check Security > Overview in the Cloudflare dashboard.

## Rate Limiting
| Endpoint Pattern | Limit | Timeout |
|-----------------|-------|---------|
| `/api/v1/auth/*` | 20 req/min per IP | 5 min block |
| `/webhooks/*` | 60 req/min per IP | 1 min block |
| `/api/v1/*` | 120 req/min per IP | 1 min block |

## Custom Rules
- Block requests with threat score > 50
- JS challenge for threat score > 10 on API paths
- Block exploit paths (`.env`, `wp-admin`, `.git`)
- Block request bodies > 1MB

## Managed Rulesets
- Cloudflare Managed Ruleset (general protection)
- OWASP ModSecurity Core Rule Set (OWASP Top 10)
