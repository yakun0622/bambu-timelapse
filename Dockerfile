FROM node:22-alpine AS web-builder

WORKDIR /web
COPY web/package*.json ./
RUN npm install
COPY web/ .
RUN npm run build


FROM python:3.12-slim

ARG USE_CN_MIRROR=true

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_DIST=/app/web/dist

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       ca-certificates \
       tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN if [ "$USE_CN_MIRROR" = "true" ]; then \
      pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --timeout 120 \
        --retries 5 \
        -r requirements.txt; \
    else \
      pip install --no-cache-dir \
        --timeout 120 \
        --retries 5 \
        -r requirements.txt; \
    fi

COPY app ./app
COPY main.py .
COPY --from=web-builder /web/dist ./web/dist

RUN mkdir -p /data/timelapse

EXPOSE 8000

CMD ["python", "main.py"]
