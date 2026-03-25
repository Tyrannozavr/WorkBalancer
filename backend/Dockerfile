FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir pip setuptools wheel

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir .

COPY alembic.ini /app/
COPY alembic /app/alembic

ENV PYTHONPATH=/app/src
CMD ["sh", "-c", "alembic upgrade head && python -m workbalancer.main"]
