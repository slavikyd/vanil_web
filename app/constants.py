"""Shared time limits (seconds)."""

# Cashier signed session cookie max-age and server-side login window.
SESSION_MAX_AGE_SECONDS = 600  # 10 minutes

# Redis cart hash TTL (refreshed on each cart mutation).
CART_TTL_SECONDS = SESSION_MAX_AGE_SECONDS

# Max length for per-line-item cashier comment (stored in Redis then orders_items.comment).
MAX_ITEM_COMMENT_LENGTH = 500
