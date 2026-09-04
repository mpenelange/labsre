FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LABSRE_MODE=replay \
    LABSRE_SCENARIO_DIR=/app/scenarios

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY scenarios ./scenarios
RUN pip install --no-cache-dir '.[llm]'

RUN useradd --create-home --uid 10001 labsre
USER labsre

EXPOSE 8000
CMD ["labsre-api"]
