import redis.asyncio as redis

# Only redis initialization here to avoid circular imports
rdb = redis.from_url("redis://rdb:6379", decode_responses=True)