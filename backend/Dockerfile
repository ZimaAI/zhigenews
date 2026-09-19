FROM docker:29-cli@sha256:018edbc908e08fcc9dbf029c812c34251e9b4719e6f71ca0e5eae2a987d014ca AS docker-cli
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN pip install --no-cache-dir uv==0.12.10
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/backend/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["uvicorn", "zhigenews.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
