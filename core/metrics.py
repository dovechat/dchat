from prometheus_client import Histogram

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