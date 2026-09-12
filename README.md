# Preflight QA

> Evidence-first pre-release quality scanning for web applications.

[![CI](https://github.com/maria-mustafa-b/qa-tester/actions/workflows/ci.yml/badge.svg)](https://github.com/maria-mustafa-b/qa-tester/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Preflight QA is an open-source scanner that opens a web application in a real browser, explores
in-scope pages and produces reproducible findings before deployment. It combines functional,
visual, content, performance, crash, accessibility and passive security signals in one JSON and
HTML report.

This repository contains the third working milestone. The current engine is deterministic; an AI
planning and triage layer will be introduced only after the underlying evidence is reliable.

## Current capabilities

- Breadth-first, same-origin crawling with page and timeout limits.
- Explicit host allowlist and blocked destructive URL patterns.
- Chromium execution across desktop and mobile viewports.
- HTTP error, failed request and browser navigation detection.
- JavaScript exception and error-level console collection.
- Full-page screenshots attached to findings.
- Horizontal overflow and off-viewport element checks.
- Automated WCAG 2.0, 2.1 and 2.2 accessibility rules powered by bundled axe-core.
- Missing titles, page language, image alt text and accessible control names.
- Passive form inspection for unsafe password submission, transport downgrade, invalid ranges and
  required controls that cannot be submitted.
- Broken image and placeholder-content detection.
- Missing security header, insecure transport and exposed credential-pattern checks.
- Configurable TTFB, FCP, LCP, CLS, transfer-size and request-count budgets.
- Declarative smoke flows with navigation, input, selection, checking and UI assertions.
- Same-scope flow navigation, blocked-path enforcement, submit guards and secret redaction.
- Screenshot baseline creation and pixel-level visual regression detection with diff evidence.
- Deterministic JSON and standalone HTML reports.
- Finding filters, category totals and per-page performance metrics in reports.
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
git clone https://github.com/maria-mustafa-b/qa-tester.git
cd qa-tester
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
metadata, inaccessible controls, placeholder text and responsive overflow. Its configured smoke
flow also verifies navigation to the healthy page.

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
accessibility_tags:
  - wcag2a
  - wcag2aa
  - wcag21aa
  - wcag22aa
performance_budgets:
  ttfb_ms: 800
  fcp_ms: 1800
  lcp_ms: 2500
  cls: 0.1
  transfer_kb: 3000
  request_count: 100
visual_regression:
  enabled: false
  baseline_dir: visual-baselines
  update_baselines: false
  max_changed_pixel_ratio: 0.01
  pixel_threshold: 25
viewports:
  - name: desktop
    width: 1440
    height: 900
  - name: mobile
    width: 390
    height: 844
flows:
  - name: healthy page navigation
    start_path: /
    viewport: desktop
    steps:
      - action: assert_visible
        selector: h1
      - action: click
        selector: 'a[href="/healthy.html"]'
      - action: assert_url
        value: /healthy.html
      - action: assert_text
        selector: main
        value: Healthy page
fail_on: high
```

`fail_on` accepts `critical`, `high`, `medium`, `low` or `never`. This lets a CI pipeline block a
release when findings meet the selected threshold.

## Smoke flows

Smoke flows test critical user journeys before the crawler begins. Supported actions are `goto`,
`click`, `fill`, `select`, `check`, `assert_visible`, `assert_text` and `assert_url`. Locators use CSS
selectors and Playwright automatically waits for elements to become actionable.

Keep credentials outside YAML by referencing environment variables:

```yaml
flows:
  - name: authorized login
    start_path: /login
    allow_submit: true
    steps:
      - action: fill
        selector: '#email'
        value_from_env: PREFLIGHT_TEST_EMAIL
      - action: fill
        selector: '#password'
        value_from_env: PREFLIGHT_TEST_PASSWORD
      - action: click
        selector: 'button[type="submit"]'
      - action: assert_url
        value: /dashboard
```

Submit-like controls are blocked unless that flow sets `allow_submit: true`. Even then, external
hosts and configured blocked paths remain prohibited. Use dedicated test accounts and never point a
flow at real payments, destructive controls or production data. Failure screenshots mask form
fields, and configured input values are excluded from structured results and redacted from errors
and recorded flow URLs.

## Visual regression baselines

Visual comparison is opt-in. Set `visual_regression.enabled: true`, then deliberately create or
refresh approved screenshots with:

```bash
preflight-qa scan \
  --config preflight.example.yml \
  --authorized \
  --update-baselines \
  --output reports/baseline-review
```

Review and commit the generated `visual-baselines/` directory. Future scans compare the same URL and
viewport against those images. Changes above `max_changed_pixel_ratio` create a visual finding with
the current screenshot, approved baseline and a red-highlighted diff. `pixel_threshold` ignores
small per-channel rendering noise. Baselines are never replaced during a normal scan.

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
           ├── Declarative smoke-flow runner
           ├── Runtime and functional evidence
           ├── Content, form and axe-core accessibility checks
           ├── Responsive visual checks
           ├── Screenshot baseline comparison
           ├── Passive security checks
           └── Browser performance budgets
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
├── flows.py         safe smoke journeys and assertions
├── models.py        report schema and finding model
├── reporting.py     JSON and HTML output
├── scanner.py       Playwright crawl and evidence collection
├── visual_regression.py  baseline image comparison and diffs
└── urls.py          URL normalization and scope controls
```

## Testing

```bash
ruff check .
pytest -q
```

The unit suite covers configuration validation, URL scope enforcement, axe result normalization,
form rules, performance budgets, flow validation, visual diffs, scope safety, secret redaction and
report creation. CI also runs a real-browser smoke-flow integration test.

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
- [x] axe-core WCAG rule integration
- [x] Browser-native Core Web Vitals and page-weight budgets
- [x] Passive form analysis
- [x] Developer-defined smoke flows
- [x] Baseline visual regression comparison
- [ ] Authenticated multi-role access-control checks
- [ ] OWASP ZAP passive-scan integration
- [ ] GitHub pull-request quality gates
- [ ] AI-assisted requirements parsing, exploratory planning and failure deduplication
- [ ] Optional local web dashboard

## Current limitations

- The scanner does not prove that a website is secure or WCAG compliant.
- Passive scanning does not submit forms or infer application-specific business rules. A smoke flow
  can submit only when explicitly enabled for that authorized flow.
- Visual baselines are viewport-specific and can still vary across operating systems, fonts and
  browser versions; establish and compare them in a consistent environment.
- Performance metrics are single synthetic browser observations, not a Lighthouse score or real-user
  field data.
- The crawler does not test native mobile or desktop applications.
- Authenticated role comparison and saved browser sessions are not implemented yet.

Automated output must be reviewed by a developer or tester before a release decision.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Security concerns should follow
the private reporting process in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
