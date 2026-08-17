"""Streaming reverse proxy for agent traffic."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request

_HOP_BY_HOP: frozenset[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def _filter_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return *headers* with all hop-by-hop entries removed.

    :param headers: raw header mapping from the request or response
    :type headers: dict[str, str]
    :return: filtered headers safe to forward
    :rtype: dict[str, str]
    """
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


async def proxy_request(
    request: Request,
    agent_url: str,
    path: str,
) -> StreamingResponse:
    """Forward *request* to *agent_url/path* and stream the response back.

    Works for JSON, SSE, and binary (tar.gz) responses without buffering.

    :param request: incoming Starlette request
    :type request: Request
    :param agent_url: base URL of the target agent (e.g. ``http://localhost:18001``)
    :type agent_url: str
    :param path: path to append to agent_url
    :type path: str
    :return: streaming response forwarded from the agent
    :rtype: StreamingResponse
    :raises HTTPException: 502 when the agent is unreachable or times out
    """
    url = f"{agent_url}/{path.lstrip('/')}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    body = await request.body()
    client = httpx.AsyncClient()

    try:
        upstream_request = client.build_request(
            method=request.method,
            url=url,
            headers=_filter_headers(dict(request.headers)),
            content=body,
        )
        # Strip any hop-by-hop headers that httpx may have added during build
        upstream_request.headers = httpx.Headers(
            _filter_headers(dict(upstream_request.headers))
        )
        response = await client.send(upstream_request, stream=True)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="agent unreachable") from exc

    async def generate() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        except httpx.TransportError:
            # Client disconnected or agent closed the stream mid-flight.
            # Response headers already sent — cannot raise HTTPException here.
            return
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        content=generate(),
        status_code=response.status_code,
        headers=_filter_headers(dict(response.headers)),
        media_type=response.headers.get("content-type"),
    )
