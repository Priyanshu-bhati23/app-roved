FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY approved ./approved
RUN pip install --no-cache-dir . && useradd --create-home runner
USER runner
EXPOSE 8000
CMD ["uvicorn", "approved.api:app", "--host", "0.0.0.0", "--port", "8000"]
