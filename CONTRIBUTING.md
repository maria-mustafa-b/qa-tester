# Contributing

Thank you for helping improve Preflight QA.

1. Open an issue describing the change or bug.
2. Create a focused branch from `main`.
3. Add or update tests for behavioural changes.
4. Run `ruff check .` and `pytest -q`.
5. Submit a pull request explaining the user impact and verification performed.

New checks must produce a stable rule ID, explain their evidence, avoid destructive behaviour and
include a test that limits false positives. Do not include real credentials, private targets or scan
reports containing sensitive data.

