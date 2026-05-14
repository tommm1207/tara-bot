FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

# Hugging Face Spaces uses port 7860
ENV PORT=7860
EXPOSE 7860

CMD ["python", "-m", "src.bot"]
