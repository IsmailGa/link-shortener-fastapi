import string

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger()

ALPHABET = string.digits + string.ascii_letters  # 0-9a-zA-Z = 62 chars
BASE = len(ALPHABET)
# Start offset to produce codes of reasonable length from the start
_COUNTER_OFFSET = 100_000_000


def encode_base62(num: int) -> str:
    """Convert a positive integer to a Base62 string."""
    if num == 0:
        return ALPHABET[0]
    encoded: list[str] = []
    while num > 0:
        num, remainder = divmod(num, BASE)
        encoded.append(ALPHABET[remainder])
    return "".join(reversed(encoded))


def decode_base62(code: str) -> int:
    """Convert a Base62 string back to an integer."""
    num = 0
    for char in code:
        num = num * BASE + ALPHABET.index(char)
    return num


async def generate_short_code(redis: Redis) -> str:
    """Generate a unique short code using a Redis atomic counter.

    Uses INCR for atomic increment, guaranteeing uniqueness
    across all workers without collision.
    """
    counter = await redis.incr("shortener:url_counter")
    code = encode_base62(counter + _COUNTER_OFFSET)
    logger.debug("short_code_generated", code=code, counter=counter)
    return code
