FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

ARG INSTALL_ML=false
COPY backend/requirements-ml.txt backend/requirements-ml.txt
RUN if [ "$INSTALL_ML" = "true" ]; then \
      pip install -r backend/requirements-ml.txt; \
    fi

# Production ONNX serving without the heavy training stack.
ARG INSTALL_ONNX=false
COPY backend/requirements-onnx.txt backend/requirements-onnx.txt
RUN if [ "$INSTALL_ONNX" = "true" ]; then \
      pip install -r backend/requirements-onnx.txt; \
    fi

COPY shared ./shared
COPY backend ./backend
COPY ml ./ml

RUN useradd --create-home --shell /usr/sbin/nologin orbit \
    && mkdir -p /app/backend/data \
    && chown -R orbit:orbit /app

USER orbit
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
