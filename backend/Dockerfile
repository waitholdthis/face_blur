# Base image is overridable for environments that must pull through a registry
# mirror (e.g. BASE_IMAGE=mirror.gcr.io/library/python:3.11-slim).
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

# No system packages required: opencv-python-headless ships its own native deps,
# which keeps this build working even on networks without access to apt mirrors.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Optional PEM bundle (build arg) for networks that intercept TLS with a
# private CA; when set it is used to verify the PyPI connection during build.
ARG EXTRA_CA_BUNDLE=""

COPY requirements.txt ./
RUN if [ -n "$EXTRA_CA_BUNDLE" ]; then \
        printf '%s\n' "$EXTRA_CA_BUNDLE" > /usr/local/share/extra-ca.crt; \
        export PIP_CERT=/usr/local/share/extra-ca.crt; \
    fi; \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
