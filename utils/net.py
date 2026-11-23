"""One shared HTTP session for the whole bot (the Roblox web APIs and Open Cloud).

Opening a new session for every request is slow and wastes connections; here every request reuses one session with
a time limit (Roblox sometimes doesn't answer at all, and the default limit of aiohttp is 5 minutes).
"""
import asyncio

import aiohttp

from utils.version import VERSION

DEFAULT_TIMEOUT = 15

_state = {"session": None, "loop": None}


class BadResponse(Exception):
    """The server answered with something that isn't the JSON it should be (e.g. a maintenance page)."""


def timeout(seconds: float = DEFAULT_TIMEOUT) -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=seconds)


def session() -> aiohttp.ClientSession:
    """The shared session of the running event loop (created on first use)."""
    loop = asyncio.get_running_loop()
    current = _state["session"]
    if current is None or current.closed or _state["loop"] is not loop:
        current = aiohttp.ClientSession(timeout=timeout(), headers={"User-Agent": f"CodeHatch/{VERSION}"})
        _state.update(session=current, loop=loop)
    return current


async def close() -> None:
    current = _state["session"]
    _state.update(session=None, loop=None)
    if current is not None and not current.closed:
        await current.close()


async def json_body(resp: aiohttp.ClientResponse):
    """The JSON of a response, or BadResponse when the body is not JSON."""
    try:
        return await resp.json(content_type=None)
    except (ValueError, aiohttp.ContentTypeError) as e:
        raise BadResponse(str(e)[:200])


async def get_json(url: str, seconds: float = DEFAULT_TIMEOUT, **kwargs):
    """(status, JSON or None). Network errors and time-outs are raised (aiohttp.ClientError, asyncio.TimeoutError);
    a 200 answer that isn't JSON raises BadResponse."""
    async with session().get(url, timeout=timeout(seconds), **kwargs) as resp:
        if resp.status != 200:
            return resp.status, None
        return resp.status, await json_body(resp)


NETWORK_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, BadResponse)
