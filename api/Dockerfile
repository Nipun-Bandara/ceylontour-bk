FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# LightGBM links against the OpenMP runtime, which the slim image does not
# ship. Without it `import lightgbm` fails with a missing libgomp.so.1.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Requirements are copied first so the layer caches between source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runs as a normal user, never root. uid 1000 matches the usual first host
# account, so the bind mount used in development stays writable and the
# training script can still save an artefact.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/ml/artifacts \
    && chown -R app:app /app
USER app

EXPOSE 8000

# gunicorn supervises the workers and restarts one that dies; the uvicorn
# worker class is what actually speaks ASGI. Development overrides this in
# docker-compose.yml with `uvicorn --reload`.
CMD ["./bootstrap.sh"]
