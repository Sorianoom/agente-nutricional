FROM python:3.13-slim
WORKDIR /app

# Node.js + npm son necesarios para instalar el CLI de Claude Code, que el
# Agent SDK invoca internamente (POST /macros/recalcular-ia).
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
