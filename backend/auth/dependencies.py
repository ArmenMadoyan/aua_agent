from fastapi import Request


async def require_auth(request: Request) -> None:
    """No-op placeholder. Wire in JWT / OAuth later."""
    pass
