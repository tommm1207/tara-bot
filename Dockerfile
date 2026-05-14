FROM python:3.12-slim

WORKDIR /app

# Copy all source files first
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN pip install --no-cache-dir .

# Hugging Face Spaces uses port 7860
ENV PORT=7860
EXPOSE 7860

CMD ["python", "-m", "src.bot"]
