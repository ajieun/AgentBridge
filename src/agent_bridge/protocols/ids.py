from __future__ import annotations

import os


def rid(prefix: str) -> str:
    return prefix + os.urandom(12).hex()
