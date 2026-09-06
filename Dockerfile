FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the core package (its pyproject.toml declares all runtime deps).
COPY packages/chatkit ./packages/chatkit
RUN pip install --no-cache-dir ./packages/chatkit

# The thin project.
COPY projects/footwear ./projects/footwear

# Make `import projects.footwear` work — projects/ is an implicit namespace
# package on PYTHONPATH (no projects/__init__.py, matching the test layout).
ENV PYTHONPATH=/app

# Drop privileges.
RUN useradd --uid 10001 --no-create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# The footwear app reads its DuckDB from a mounted volume at runtime; nothing
# is baked. The app imports and boots without a DB present, so /healthz is safe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

# --proxy-headers so request.url.scheme is https behind Traefik (Secure cookie).
CMD ["uvicorn", "projects.footwear.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
