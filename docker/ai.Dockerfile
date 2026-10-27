# Minimal runtime image for the optional ShopLens AI service.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/vnecom
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ai]" \
 && useradd --system --create-home --uid 10001 vnecom
USER vnecom
EXPOSE 8000
ENTRYPOINT ["vnecom"]
CMD ["ai", "serve", "--host", "0.0.0.0", "--port", "8000"]
