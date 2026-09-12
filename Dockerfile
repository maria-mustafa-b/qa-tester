FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY preflight_qa ./preflight_qa
RUN pip install --no-cache-dir .

ENTRYPOINT ["preflight-qa"]
CMD ["--help"]

