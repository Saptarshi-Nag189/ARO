# Security Policy

## Supported Versions

The ARO (Autonomous Research Operator) project is under active development. We recommend always running the `main` branch or the latest numbered release. Older versions are not actively backported for security fixes.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| >= 1.0.0| :white_check_mark: |
| < 1.0.0 | :x:                |

## Reporting a Vulnerability

Security is a high priority for the ARO project. If you discover a vulnerability, misconfiguration, or security risk:

1. **Do not open a public issue.** Public disclosure before a fix is available puts users at risk.
2. Please report the vulnerability privately via [GitHub Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) on this repository.
3. If private reporting is disabled, please email the maintainer directly.

### What to include

- A detailed description of the vulnerability and its impact.
- Steps to reproduce the issue (including any malicious inputs or configurations).
- (Optional but helpful) A suggested mitigation or patch.

### What to expect

- You should expect an initial acknowledgement within **48 hours**.
- We will triage the issue and determine the severity.
- If accepted, we will coordinate with you to issue a patch and potentially an advisory crediting your discovery.
- We aim to resolve High/Critical vulnerabilities within **7 days** of verification.
