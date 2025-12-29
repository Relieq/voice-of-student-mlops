from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import (
    Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, multiprocess
)
from starlette.responses import Response
import os
import time
import random

APP_VERSION = os.getenv("APP_VERSION", "v1")
CHAOS_MODE = os.getenv("CHAOS_MODE", "0") == "1"

app = FastAPI(title="Voice of Student - Model Service", version=APP_VERSION)

REQ_COUNT = Counter("http_requests_total",
                    "Total HTTP requests",
                    ["path", "method", "status", "version"])
REQ_LAT = Histogram("http_request_latency_seconds",
                    "Request latency",
                    ["path", "method", "version"])

class PredictIn(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}

@app.get("/metrics")
def metrics():
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

@app.post("/predict")
def predict(payload: PredictIn):
    start = time.time()
    status = "200"
    try:
        # Stub: giả lập inference
        if CHAOS_MODE:
            # Giả lập latency + lỗi theo tải (để demo canary/rollback sau)
            time.sleep(random.uniform(0.15, 0.45))
            if random.random() < 0.3:
                raise RuntimeError("simulated failure")

        result = {
            "version": APP_VERSION,
            "topic": {"label": "facility", "confidence": 0.55},
            "sentiment": {"label": "negative", "confidence": 0.62},
        }
        return result
    except Exception:
        status = "500"
        raise
    finally:
        elapsed = time.time() - start
        REQ_COUNT.labels("/predict", "POST", status, APP_VERSION).inc()
        REQ_LAT.labels("/predict", "POST", APP_VERSION).observe(elapsed)
