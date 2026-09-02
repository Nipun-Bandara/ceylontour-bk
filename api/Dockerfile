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

# docker-compose mounts the source over this in development. The COPY is here
# so the image also runs on its own on the demo machine.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
