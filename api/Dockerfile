FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt /app/requirements.txt
ARG PIP_INDEX_URL

RUN if [ -n "$PIP_INDEX_URL" ]; then \
      pip config set global.index-url "$PIP_INDEX_URL"; \
    fi && \
    pip install --no-cache-dir -r requirements.txt

COPY api/ /app/api/

RUN mkdir -p /app/data

EXPOSE 9000

CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "9000"]
