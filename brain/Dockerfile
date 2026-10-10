FROM python:3.12-slim

WORKDIR /srv
RUN pip install --no-cache-dir "mcp>=1.9,<2" "psycopg[binary]>=3.2"
COPY app /srv/app

EXPOSE 8000
CMD ["python", "-m", "app.server"]
