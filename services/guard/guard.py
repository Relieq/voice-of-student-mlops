import os
import time
import requests
import docker

PROM_URL = os.getenv("PROM_URL", "http://prometheus:9090")
CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "30"))

# SLO thresholds
ERR_RATE_THRESHOLD = float(os.getenv("ERR_RATE_THRESHOLD", "0.01"))  # 1%
P95_THRESHOLD_SEC = float(os.getenv("P95_THRESHOLD_SEC", "0.35"))  # 350ms

# anti-flap: cần fail liên tiếp N lần mới rollback
FAIL_STREAK_TO_ROLLBACK = int(os.getenv("FAIL_STREAK_TO_ROLLBACK", "2"))

ROUTER_CONTAINER = os.getenv("ROUTER_CONTAINER", "vos-router")
ROUTER_CANARY_CONF = os.getenv("ROUTER_CANARY_CONF", "/etc/nginx/router/nginx_canary.conf")
ROUTER_STABLE_CONF = os.getenv("ROUTER_STABLE_CONF", "/etc/nginx/router/nginx_stable.conf")
ROUTER_TARGET_CONF = os.getenv("ROUTER_TARGET_CONF", "/etc/nginx/nginx.conf")


def prom_query(q: str) -> float:
    r = requests.get(f"{PROM_URL}/api/v1/query", params={"query": q}, timeout=10)
    r.raise_for_status()
    data = r.json()
    # Ví dụ cho cấu trúc data trả về:
    # {
    #     "status": "success",
    #     "data": {
    #         "resultType": "vector",
    #         "result": [
    #             {
    #                 "metric": {
    #                     "__name__": "http_requests_total",
    #                     "version": "v2",
    #                     "status": "500",
    #                     "path": "/predict"
    #                 },
    #                 "value": [1735460000.123, "0.02"]  # [timestamp, value as string]
    #             }
    #         ]
    #     }
    # }

    result = data.get("data", {}).get("result", [])
    if not result:
        return float("nan")
    # lấy sample đầu tiên
    return float(result[0]["value"][1])


def set_router_mode(mode: str):
    """mode: 'canary' or 'stable'"""
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    c = client.containers.get(ROUTER_CONTAINER)

    src = ROUTER_CANARY_CONF if mode == "canary" else ROUTER_STABLE_CONF
    cmd = f"sh -c 'cp {src} {ROUTER_TARGET_CONF} && nginx -t && nginx -s reload'"
    exit_code, output = c.exec_run(cmd)
    out_text = output.decode("utf-8", errors="ignore") if isinstance(output, (bytes, bytearray)) else str(output)
    print(f"[guard] switch router -> {mode}, exit={exit_code}\n{out_text}")


def main():
    # PromQL:
    # error rate v2 (path=/predict) trong 1 phút
    q_err = (
        'sum(rate(http_requests_total{version="v2",path="/predict",status="500"}[1m])) '
        '/ '
        'sum(rate(http_requests_total{version="v2",path="/predict"}[1m]))'
    )

    # p95 latency v2 (seconds) trong 1 phút từ histogram bucket
    q_p95 = (
        'histogram_quantile(0.95, '
        'sum(rate(http_request_latency_seconds_bucket{version="v2",path="/predict",method="POST"}[1m])) by (le)'
        ')'
    )

    q_v2_rps = 'sum(rate(http_requests_total{version = "v2", path = "/predict"}[1m]))'

    fail_streak = 0
    rolled_back = False

    print("[guard] started. monitoring v2 SLO...")
    while True:
        try:
            v2_rps = prom_query(q_v2_rps)
            if (v2_rps != v2_rps) or (v2_rps <= 0):  # NaN check + very low traffic
                print(f"[guard] v2 RPS={v2_rps:.2f}, skipping SLO check")
                time.sleep(CHECK_INTERVAL_SEC)
                continue
            else:
                print(f"[guard] v2 RPS={v2_rps:.2f}, checking SLO...")

            err_rate = prom_query(q_err)
            p95 = prom_query(q_p95)

            # khi không có traffic v2, err_rate có thể NaN do chia 0
            err_rate_ok = (err_rate == err_rate) and (err_rate <= ERR_RATE_THRESHOLD)  # NaN check
            p95_ok = (p95 == p95) and (p95 <= P95_THRESHOLD_SEC)

            print(f"[guard] v2 err_rate={err_rate:.4f} (<= {ERR_RATE_THRESHOLD}?), "
                  f"p95={p95:.3f}s (<= {P95_THRESHOLD_SEC}?)")

            if err_rate_ok and p95_ok:
                fail_streak = 0
            else:
                fail_streak += 1
                print(f"[guard] SLO violation streak: {fail_streak}/{FAIL_STREAK_TO_ROLLBACK}")

            if (not rolled_back) and fail_streak >= FAIL_STREAK_TO_ROLLBACK:
                print("[guard] rollback triggered!")
                set_router_mode("stable")
                rolled_back = True

        except Exception as e:
            print(f"[guard] error: {e}")

        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
