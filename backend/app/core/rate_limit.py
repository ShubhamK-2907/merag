"""Per-IP rate limiting (slowapi). In-memory storage: fine for one instance;
switch `storage_uri` to Redis when scaling horizontally."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
