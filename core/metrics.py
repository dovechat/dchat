from prometheus_client import Counter, Gauge, Histogram

import logging
log = logging.getLogger("uvicorn.error")

webhook_processing_seconds = Histogram(
    "dovechat_webhook_processing_seconds",
    "Time spent processing incoming webhooks",
    ["channel_type", "event_type"],
)

webhook_errors_total = Counter(
    "dovechat_webhook_requests_total",
    "Webhook requests by status",
    ["channel_type", "status"],
)

provider_status = Gauge(
    "dovechat_provider_status",
    "Provider connection status (1=connected, 0=not connected)",
    ["channel_type"],
)




from functools import wraps
from core.metrics import webhook_processing_seconds, webhook_errors_total

def prometheus_metrics(channel_type: str, event_type: str = "message"):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                with webhook_processing_seconds.labels(channel_type=channel_type, event_type=event_type).time():
                    log.info(f"prometheus_metrics wrap channel_type {channel_type} event_type {event_type} ")
                    result = await func(*args, **kwargs)
                    log.info(f"eng prometheus_metrics wrap channel_type {channel_type} event_type {event_type} ")
                webhook_errors_total.labels(channel_type=channel_type, status="success").inc()
                return result
            except Exception:
                webhook_errors_total.labels(channel_type=channel_type, status="error").inc()
                raise
        return wrapper
    return decorator

