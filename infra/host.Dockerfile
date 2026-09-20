FROM python:3.11-slim

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/host apps/host
COPY apps/__init__.py apps/__init__.py
COPY packages packages
COPY jobs jobs
COPY fixtures fixtures

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "apps.host"]
