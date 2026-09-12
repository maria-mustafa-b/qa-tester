# Preflight QA

> Evidence-first pre-release quality scanning for web applications.

[![CI](https://github.com/maria-mustafa-b/preflight-qa/actions/workflows/ci.yml/badge.svg)](https://github.com/maria-mustafa-b/preflight-qa/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Preflight QA is an open-source scanner that opens a web application in a real browser, explores
in-scope pages and produces reproducible findings before deployment. It combines functional,
visual, content, performance, crash, accessibility and passive security signals in one JSON and
HTML report.

This repository contains the first working milestone. The current engine is deterministic; an AI
planning and triage layer will be introduced only after the underlying evidence is reliable.

## Current capabilities

- Breadth-first, same-origin crawling with page and timeout limits.
- Explicit host allowlist and blocked destructive URL patterns.
- Chromium execution across desktop and mobile viewports.
- HTTP error, failed request and browser navigation detection.
- JavaScript exception and error-level console collection.
- Full-page screenshots attached to findings.
- Horizontal overflow and off-viewport element checks.
- Missing titles, page language, image alt text and accessible control names.
- Broken image and placeholder-content detection.
- Missing security header, insecure transport and exposed credential-pattern checks.
- Basic page performance budget for DOM content loading.
- Deterministic JSON and standalone HTML reports.
- CI-friendly exit codes based on configurable severity.

## Safety model

Only test applications you own or have explicit permission to assess. The CLI requires an
`--authorized` confirmation. The crawler uses safe browser navigation and blocks common destructive
paths by default. It does **not** exploit vulnerabilities, submit forms, brute-force accounts or run
active injection attacks.

Treat test credentials as secrets. Keep them in environment variables and never commit them.

## Quick start

Requirements:

- Python 3.11 or newer
- Linux, macOS or Windows

```bash
git clone https://github.com/maria-mustafa-b/preflight-qa.git
cd preflight-qa
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Run a scan:

```bash
preflight-qa scan \
  --url http://127.0.0.1:3000 \
  --authorized \
  --output reports/local
```

Open `reports/local/report.html` in a browser after the scan completes.

## Try the deliberately imperfect demo

Terminal one:

```bash
python -m http.server 8080 --directory demo_site
```

Terminal two:

```bash
preflight-qa scan \
  --config preflight.example.yml \
  --authorized \
  --output reports/demo
```

The demo intentionally contains a JavaScript exception, a broken link, a broken image, missing
metadata, inaccessible controls, placeholder text and responsive overflow. It exists only to verify
that findings and evidence are generated correctly.

## Configuration

Copy `preflight.example.yml` and adjust the values:

```yaml
target: http://127.0.0.1:8080
max_pages: 20
timeout_ms: 10000
headless: true
ignore_https_errors: false
allowed_hosts:
  - 127.0.0.1
blocked_url_patterns:
  - /logout
  - /delete
  - /remove
  - /purchase
viewports:
  - name: desktop
    width: 1440
    height: 900
  - name: mobile
    width: 390
    height: 844
fail_on: high
```

`fail_on` accepts `critical`, `high`, `medium`, `low` or `never`. This lets a CI pipeline block a
release when findings meet the selected threshold.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Scan completed and did not meet the configured failure threshold |
| `1` | Scan completed and findings met the failure threshold |
| `2` | Invalid input, missing authorization or scanner failure |
| `130` | Scan cancelled with Ctrl+C |

## Architecture

```text
CLI
 └── Configuration and scope validation
      └── Playwright crawler
           ├── Runtime and functional evidence
           ├── Content and accessibility checks
           ├── Responsive visual checks
           ├── Passive security checks
           └── Performance budget
                └── Normalized findings
                     ├── report.json
                     └── report.html + screenshots
```

The modules deliberately separate collection from reporting:

```text
preflight_qa/
├── checks/          deterministic quality rules
├── templates/       HTML report template
├── cli.py           command-line interface and exit codes
├── config.py        typed YAML configuration
├── models.py        report schema and finding model
├── reporting.py     JSON and HTML output
├── scanner.py       Playwright crawl and evidence collection
└── urls.py          URL normalization and scope controls
```

## Testing

```bash
ruff check .
pytest -q
```

The unit suite covers configuration validation, URL scope enforcement, deterministic checks, secret
redaction and report creation. Browser-level integration tests will be added alongside the next
milestone.

## Report semantics

Every finding includes:

- Stable rule ID
- Category and severity
- Confidence level
- Page and viewport
- Description and recommendation
- Structured evidence
- Screenshot when available

The scanner distinguishes application findings from scanner errors. Credential-shaped evidence is
redacted before it is written to disk.

## Roadmap

- [x] Safe crawler and evidence collection
- [x] Functional, crash, content, responsive and passive security baseline
- [x] JSON and HTML reports
- [ ] axe-core WCAG rule integration
- [ ] Lighthouse/Core Web Vitals integration
- [ ] Forms and developer-defined smoke flows
- [ ] Baseline visual regression comparison
- [ ] Authenticated multi-role access-control checks
- [ ] OWASP ZAP passive-scan integration
- [ ] GitHub pull-request quality gates
- [ ] AI-assisted requirements parsing, exploratory planning and failure deduplication
- [ ] Optional local web dashboard

## Current limitations

- The scanner does not prove that a website is secure or WCAG compliant.
- It does not currently submit forms or infer application-specific business rules.
- Visual checks use browser geometry; pixel-baseline comparison is planned.
- Performance currently measures navigation timing rather than full Lighthouse audits or load.
- The crawler does not test native mobile or desktop applications.
- Dynamic applications may require authentication and workflow definitions in future releases.

Automated output must be reviewed by a developer or tester before a release decision.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Security concerns should follow
the private reporting process in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).

