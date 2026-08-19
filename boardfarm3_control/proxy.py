"""Streaming reverse proxy for agent traffic."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request

_log = logging.getLogger(__name__)

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


def is_streaming_path(path: str) -> bool:
    """Report whether *path* names a long-lived streaming endpoint.

    Streaming endpoints must not carry a read timeout: an SSE console stream
    is legitimately idle for minutes, and a bounded read severs it.

    :param path: sub-path being proxied, e.g. ``"console/stream"``
    :type path: str
    :return: True when the response is expected to stream
    :rtype: bool
    """
    clean = path.split("?", 1)[0].strip("/")
    return (
        clean.endswith("stream")
        or clean == "diagnostics"
        or clean.startswith("diagnostics/")
    )


def _client_or_default(
    client: httpx.AsyncClient | None,
) -> tuple[httpx.AsyncClient, bool]:
    """Return a usable client and whether this call owns closing it.

    :param client: pooled client supplied by the caller, or None
    :type client: httpx.AsyncClient | None
    :return: tuple of (client to use, True when a new client was created here)
    :rtype: tuple[httpx.AsyncClient, bool]
    """
    if client is None:
        return httpx.AsyncClient(), True
    return client, False


def _timeout_for(path: str) -> httpx.Timeout:
    """Build the httpx timeout appropriate for *path*.

    :param path: sub-path being proxied
    :type path: str
    :return: timeout configuration
    :rtype: httpx.Timeout
    """
    connect = float(os.environ.get("BOARDFARM_PROXY_CONNECT_TIMEOUT", "10"))
    read = (
        None
        if is_streaming_path(path)
        else float(os.environ.get("BOARDFARM_PROXY_READ_TIMEOUT", "1800"))
    )
    return httpx.Timeout(connect=connect, read=read, write=30.0, pool=10.0)


async def proxy_request(  # noqa: PLR0913
    request: Request,
    agent_url: str,
    path: str,
    body: bytes | None = None,
    client: httpx.AsyncClient | None = None,
    session_id: str = "",  # noqa: ARG001
) -> StreamingResponse:
    """Forward *request* to *agent_url/path* and stream the response back.

    Works for JSON, SSE, and binary (tar.gz) responses without buffering.
    When *body* is provided it is forwarded instead of the original request
    body; the stale ``content-length`` header is stripped so httpx can set
    the correct value for the override payload.

    :param request: incoming Starlette request
    :type request: Request
    :param agent_url: base URL of the target agent (e.g. ``http://localhost:18001``)
    :type agent_url: str
    :param path: path to append to agent_url
    :type path: str
    :param body: optional body bytes to forward instead of the original
    :type body: bytes | None
    :param client: pooled client to use; a per-request client is created when None
    :type client: httpx.AsyncClient | None
    :param session_id: session this request belongs to, used in error frames
    :type session_id: str
    :return: streaming response forwarded from the agent
    :rtype: StreamingResponse
    :raises HTTPException: 502 when the agent is unreachable or times out
    """
    url = f"{agent_url}/{path.lstrip('/')}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    raw = body if body is not None else await request.body()
    forwarded_headers = _filter_headers(dict(request.headers))
    if body is not None:
        forwarded_headers.pop("content-length", None)
    client, owns_client = _client_or_default(client)

    try:
        upstream_request = client.build_request(
            method=request.method,
            url=url,
            headers=forwarded_headers,
            content=raw,
            timeout=_timeout_for(path),
        )
        # Strip any hop-by-hop headers that httpx may have added during build
        upstream_request.headers = httpx.Headers(
            _filter_headers(dict(upstream_request.headers))
        )
        response = await client.send(upstream_request, stream=True)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        if owns_client:
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
            if owns_client:
                await client.aclose()

    return StreamingResponse(
        content=generate(),
        status_code=response.status_code,
        headers=_filter_headers(dict(response.headers)),
        media_type=response.headers.get("content-type"),
    )
