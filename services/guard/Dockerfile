FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY guard.py /app/guard.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/guard.py"]