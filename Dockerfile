# PriceScout dashboard (+ scrape/simulate/analysis scripts) on CPU. MLX fine-tuning and the
# fine-tuned matcher need Apple Silicon, so Phase 3 stays on the host; the LLM is reached via
# Ollama on the host.
#
#   docker build -t pricescout .
#   docker run -p 8501:8501 -v "$PWD/data:/app/data" \
#     -e OLLAMA_BASE_URL=http://host.docker.internal:11434 pricescout
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY app ./app
COPY scripts ./scripts
COPY .streamlit ./.streamlit

ENV DB_PATH=/app/data/pricescout.duckdb
EXPOSE 8501
CMD ["streamlit", "run", "app/dashboard.py", "--server.address=0.0.0.0", "--server.port=8501"]
