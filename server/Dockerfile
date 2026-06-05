FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# system deps for shapely (libgeos)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# install python deps first for layer caching
COPY server/requirements.txt /tmp/requirements.txt
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r /tmp/requirements.txt \
    shapely==2.0.6 \
    watchfiles==0.24.0

# project layout: keep server/ and gym/ siblings under /app so
# server/app/tianshu_runtime/runtime.py can resolve parents[3]/gym
COPY server /app/server
COPY gym /app/gym
COPY client/src/scenarios /app/client/src/scenarios

WORKDIR /app/server

FROM base AS test

RUN pip install -i https://pypi.org/simple \
    -r requirements-dev.txt

CMD ["pytest"]

FROM base AS runtime

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
