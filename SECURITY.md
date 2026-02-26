# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `main` branch | ✅ |
| >= 2.0.0 | ✅ |
| < 2.0.0 | ❌ |

## Security Features

ARO implements the following security measures:

| Feature | Implementation |
|---|---|
| **API Authentication** | `X-API-Key` header on all `/api/` endpoints (optional, configurable via `ARO_API_KEY`) |
| **SSRF Protection** | URL validation before web requests |
| **CORS** | Restricted to known origins (`localhost:5173`, `localhost:3000`) |
| **Security Headers** | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, CSP |
| **Path Traversal Defense** | Session IDs validated with strict regex (`^session_[a-f0-9]{12}$`) |
| **Concurrent Session Limits** | Configurable via `ARO_MAX_CONCURRENT` (default: 3) |
| **Secret Management** | `.env` file in `.gitignore`, separate keys per model provider |
| **Reasoning Isolation** | Hard guard prevents reasoning traces from leaking into production output |
| **Health Endpoint** | `/api/health` bypasses auth for load balancer probes |

## API Key Configuration

ARO supports per-model API keys to limit blast radius if a key is compromised:

```env
OPENROUTER_API_KEY=...          # Trinity (research, innovation, orchestrator)
OPENROUTER_API_KEY_STEP=...     # Step 3.5 Flash (planner, claim extraction)
OPENROUTER_API_KEY_GPT_OSS=...  # GPT-OSS-120B (skeptic, synthesis, reflection)
```

The management key (`OPENROUTER_MGMT_KEY`) is **never** used for model requests.

## Reporting a Vulnerability

1. **Do not open a public issue.** Public disclosure before a fix is available puts users at risk.
2. Report via [GitHub Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) on this repository.
3. If private reporting is unavailable, email the maintainer directly.

### What to Include

- Description of the vulnerability and its impact
- Steps to reproduce (including malicious inputs or configurations)
- Suggested mitigation or patch (optional but helpful)

### Response Timeline

- **48 hours** — initial acknowledgement
- **7 days** — patch for High/Critical vulnerabilities
- Credit in advisory if desired
