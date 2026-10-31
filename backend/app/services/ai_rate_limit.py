"""
Superseded by app/services/usage.py.

The previous limiter kept its counters in process memory (lost on restart, not
shared between API instances) and keyed them on a client-supplied header. AI
usage is now limited per signed-in user per day, in PostgreSQL — see
usage.consume_ai_request. Nothing imports this module any more; it is kept only
so an old import fails loudly instead of silently disabling protection.
"""

raise ImportError(
    "app.services.ai_rate_limit was replaced by app.services.usage.consume_ai_request"
)
