# session_id Body Param Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `session_id` from a URL path parameter to the JSON request body for POST plugin/template proxy routes in the boardfarm control plane.

**Architecture:** The control plane proxy wraps agent routes by prepending `/sessions/{session_id}/` to their paths and injecting `session_id` as a FastAPI path parameter. After this change, the path prefix is dropped entirely and `session_id` is added as a required field to each route's Pydantic request body. The proxy extracts it, strips it from the forwarded payload, and resolves the downstream agent. GET catch-all routes (`/sessions/{session_id}/{path:path}`) and the session lifecycle `DELETE /sessions/{session_id}` are not changed.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, httpx, pytest, respx (HTTP mock)

## Global Constraints

- Python 3.11–3.13 compatible syntax only — no 3.12+ exclusive syntax
- `ruff`, `flake8`, `mypy --disallow-untyped-defs` must pass — full type annotations required on every new/changed function
- Docstrings are sphinx-style with `:param:` / `:type:` / `:return:` / `:rtype:` for all public functions
- Conventional commit messages: `fix(openapi): …`, `fix(proxy): …`, `test(control): …`
- Do not modify `boardfarm3_control/app.py`, `boardfarm3/api/routers/_generator.py`, or integration tests

---

## File Map

| File | Role |
|---|---|
| `boardfarm3_control/proxy.py` | Add optional `body` override; strip stale `content-length` when used |
| `boardfarm3_control/openapi.py` | Rebuild proxy endpoint signature (body model extension, not path param); fix route path and downstream path computation |
| `unittests/control/test_proxy.py` | New test for body override behaviour |
| `unittests/control/test_openapi.py` | Rename+update assertion: session_id no longer in path |
| `unittests/control/test_proxy_path_params.py` | Update call site: new URL, session_id in body |

---

### Task 1: Extend `proxy_request` with optional body override

**Files:**
- Modify: `boardfarm3_control/proxy.py`
- Test: `unittests/control/test_proxy.py`

**Interfaces:**
- Produces: `proxy_request(request, agent_url, path, body=None)` — when `body` is not `None`, use it as the forwarded payload and strip `content-length` from forwarded headers

---

- [ ] **Step 1: Write the failing test**

  In `unittests/control/test_proxy.py`, add two module-level route definitions
  directly after the `_client = TestClient(...)` line, then add the two new
  test functions at the end of the file.

  **Route definitions (add after `_client = TestClient(_proxy_app, raise_server_exceptions=True)`):**

  ```python
  @_proxy_app.post("/override-test/{path:path}")
  async def _override_route(path: str, request: Request) -> object:
      return await proxy_request(request, "http://fake-agent", path, body=b'{"x": 1}')


  @_proxy_app.post("/cl-test/{path:path}")
  async def _cl_route(path: str, request: Request) -> object:
      return await proxy_request(request, "http://fake-agent", path, body=b'{"x": 1}')
  ```

  **Test functions (add at end of file):**

  ```python
  @respx.mock
  def test_proxy_uses_body_override_instead_of_request_body() -> None:
      """When body override is provided it is forwarded instead of the original."""
      captured: dict[str, bytes] = {}

      def capture(req: httpx.Request) -> httpx.Response:
          captured["body"] = req.content
          return httpx.Response(200, json={})

      respx.post("http://fake-agent/action").mock(side_effect=capture)

      resp = _client.post("/override-test/action", json={"original": "ignored"})
      assert resp.status_code == 200
      assert captured["body"] == b'{"x": 1}'


  @respx.mock
  def test_proxy_body_override_sets_correct_content_length() -> None:
      """content-length forwarded to the agent must match the override body."""
      captured_headers: dict[str, str] = {}

      def capture(req: httpx.Request) -> httpx.Response:
          captured_headers.update(dict(req.headers))
          return httpx.Response(200, json={})

      respx.post("http://fake-agent/action").mock(side_effect=capture)

      _client.post("/cl-test/action", json={"original": "longer payload here"})
      # The override body is b'{"x": 1}' (8 bytes); httpx computes content-length
      # from it, not from the larger original request body.
      assert captured_headers.get("content-length") == str(len(b'{"x": 1}'))
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  pytest unittests/control/test_proxy.py::test_proxy_uses_body_override_instead_of_request_body unittests/control/test_proxy.py::test_proxy_body_override_strips_content_length_header -v
  ```

  Expected: `TypeError` or similar — `proxy_request` does not yet accept a `body` keyword argument.

- [ ] **Step 3: Implement the change in `proxy_request`**

  Replace the current signature and body-read line in `boardfarm3_control/proxy.py`:

  ```python
  async def proxy_request(
      request: Request,
      agent_url: str,
      path: str,
      body: bytes | None = None,
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
      client = httpx.AsyncClient()

      try:
          upstream_request = client.build_request(
              method=request.method,
              url=url,
              headers=forwarded_headers,
              content=raw,
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
  ```

- [ ] **Step 4: Run the new tests to verify they pass**

  ```bash
  pytest unittests/control/test_proxy.py -v
  ```

  Expected: all tests in `test_proxy.py` pass.

- [ ] **Step 5: Commit**

  ```bash
  git add boardfarm3_control/proxy.py unittests/control/test_proxy.py
  git commit -m "fix(proxy): add optional body override and strip stale content-length"
  ```

---

### Task 2: Rebuild proxy endpoint — session_id from path to body

**Files:**
- Modify: `boardfarm3_control/openapi.py`
- Test (update existing): `unittests/control/test_proxy_path_params.py`
- Test (update existing): `unittests/control/test_openapi.py`

**Interfaces:**
- Consumes: `proxy_request(..., body=stripped_bytes)` from Task 1
- Produces:
  - Plugin routes registered at `/{route.path}` (no `/sessions/{session_id}/` prefix)
  - Each route's Pydantic body model extended with a required `session_id: str` field
  - `proxy_endpoint` extracts `session_id` from `kwargs["body"].session_id`

---

- [ ] **Step 1: Update `test_proxy_path_params.py` — call site and body**

  The test currently posts to `/sessions/s-1/core/templates/lan/0/get_interface_stats`
  with body `{"iface": "eth1"}`.

  Replace the entire `test_proxy_substitutes_index_path_param_into_downstream_url`
  function with:

  ```python
  @respx.mock
  def test_proxy_substitutes_index_path_param_into_downstream_url() -> None:
      """The agent receives the substituted index, not the literal ``{index}``."""
      captured: dict[str, str] = {}

      def capture(request: Request) -> httpx.Response:
          captured["path"] = request.url.path
          return httpx.Response(200, json={"result": {}})

      respx.route(host="agent.local").mock(side_effect=capture)

      resp = _client().post(
          "/core/templates/lan/0/get_interface_stats",
          json={"session_id": "s-1", "iface": "eth1"},
      )

      assert resp.status_code == 200
      assert captured["path"] == "/core/templates/lan/0/get_interface_stats"
      assert "{index}" not in captured["path"]
  ```

- [ ] **Step 2: Update `test_openapi.py` — rename and rewrite the session_id path test**

  Replace `test_plugin_route_is_prefixed_with_session_id` (lines 57–64) with:

  ```python
  def test_plugin_route_has_session_id_in_body_not_path() -> None:
      app = _app_with_plugin()
      client = TestClient(app)
      schema = client.get("/openapi.json").json()
      # Plugin paths must NOT carry {session_id} in the URL any more
      plugin_paths = [p for p in schema["paths"] if "ping" in p]
      assert len(plugin_paths) >= 1
      assert all("/sessions/{session_id}/" not in p for p in plugin_paths)
      # The route is served at its original path (no /sessions/ prefix)
      assert any(p.endswith("/use-cases/networking/ping") for p in plugin_paths)
      # session_id field must appear in the request body schema
      schema_str = str(schema)
      assert "session_id" in schema_str
  ```

- [ ] **Step 3: Run the updated tests to verify they fail (as expected before implementation)**

  ```bash
  pytest unittests/control/test_proxy_path_params.py unittests/control/test_openapi.py::test_plugin_route_has_session_id_in_body_not_path -v
  ```

  Expected: both fail — the routes still embed `session_id` in the path.

- [ ] **Step 4: Implement the changes in `openapi.py`**

  Replace `_make_proxy_endpoint` and `register_plugin_routes` with the following.
  Add `import json as _json` to the top-level imports block.
  Add `from pydantic import create_model` to the top-level imports block.

  **`_make_proxy_endpoint` — full replacement:**

  ```python
  def _make_proxy_endpoint(
      original_endpoint: Any,  # noqa: ANN401
      registry: SessionRegistry,
  ) -> Any:  # noqa: ANN401
      """Return a proxy handler that preserves the original endpoint's signature.

      FastAPI reads ``__signature__`` via ``inspect.signature()`` to generate the
      OpenAPI schema.  The wrapper has the same signature as ``original_endpoint``
      with ``session_id: str`` injected into the Pydantic body model and
      ``request: Request`` ensured present.  At runtime the proxy extracts
      ``session_id`` from the body, strips it, and forwards the remainder to the
      downstream agent.

      :param original_endpoint: the plugin's async handler function
      :type original_endpoint: Any
      :param registry: registry used to resolve the agent URL
      :type registry: SessionRegistry
      :return: proxy async function with adjusted signature
      :rtype: Any
      """
      from boardfarm3_control.proxy import proxy_request

      try:
          resolved_hints = typing.get_type_hints(original_endpoint)
      except Exception:  # noqa: BLE001
          resolved_hints = {}

      sig = inspect.signature(original_endpoint)
      existing_params: list[inspect.Parameter] = [
          p.replace(annotation=resolved_hints[p.name])
          if p.name in resolved_hints and p.annotation is not inspect.Parameter.empty
          else p
          for p in sig.parameters.values()
      ]

      # Extend the Pydantic body model with a required session_id field.
      body_idx = next(
          (i for i, p in enumerate(existing_params) if p.name == "body"),
          None,
      )
      if body_idx is not None:
          original_model = existing_params[body_idx].annotation
          if hasattr(original_model, "model_fields"):
              proxied_model = create_model(
                  f"Proxied{original_model.__name__}",
                  session_id=(str, ...),
                  **{
                      name: (fi.annotation, fi)
                      for name, fi in original_model.model_fields.items()
                  },
              )
              existing_params[body_idx] = existing_params[body_idx].replace(
                  annotation=proxied_model
              )

      # Ensure request is present; do not add a separate session_id path param.
      new_params: list[inspect.Parameter] = []
      if not any(p.name == "request" for p in existing_params):
          new_params.append(
              inspect.Parameter(
                  "request",
                  inspect.Parameter.POSITIONAL_OR_KEYWORD,
                  annotation=Request,
              ),
          )
      new_params.extend(existing_params)
      new_sig = sig.replace(parameters=new_params)

      async def proxy_endpoint(**kwargs: Any) -> Any:  # noqa: ANN401
          body: Any = kwargs["body"]  # noqa: ANN401
          request: Request = kwargs["request"]
          session_id: str = body.session_id
          info = registry.get(session_id)
          if info is None:
              raise HTTPException(status_code=404, detail=f"unknown session {session_id}")
          stripped = body.model_dump(exclude={"session_id"})
          stripped_bytes = _json.dumps(stripped).encode()
          downstream_path = request.url.path.lstrip("/")
          return await proxy_request(
              request, info.agent_url, downstream_path, body=stripped_bytes
          )

      proxy_endpoint.__signature__ = new_sig  # type: ignore[attr-defined]
      proxy_endpoint.__name__ = f"proxy_{original_endpoint.__name__}"
      proxy_endpoint.__doc__ = original_endpoint.__doc__
      return proxy_endpoint
  ```

  **`register_plugin_routes` — update route path only (one line change):**

  Change:
  ```python
  new_path = f"/sessions/{{session_id}}/{route.path.lstrip('/')}"
  ```
  To:
  ```python
  new_path = f"/{route.path.lstrip('/')}"
  ```

  Also update the docstring first line from:
  > Wrap plugin routes as proxy-dispatch endpoints under ``/sessions/{session_id}/``.

  To:
  > Wrap plugin routes as proxy-dispatch endpoints, injecting ``session_id`` into each body model.

- [ ] **Step 5: Add `import json as _json` and `from pydantic import create_model` to `openapi.py` imports**

  At the top of `boardfarm3_control/openapi.py`, the existing imports end with:
  ```python
  from fastapi import APIRouter, HTTPException
  from fastapi.routing import APIRoute
  from starlette.requests import Request
  ```

  Add after those lines:
  ```python
  import json as _json

  from pydantic import create_model
  ```

- [ ] **Step 6: Run the updated tests to verify they pass**

  ```bash
  pytest unittests/control/test_proxy_path_params.py unittests/control/test_openapi.py -v
  ```

  Expected: all tests in both files pass.

- [ ] **Step 7: Run the full control unit test suite**

  ```bash
  pytest unittests/control/ -v
  ```

  Expected: all tests pass. If `test_app.py` or `test_openapi.py` have failures unrelated to the changed tests, investigate before proceeding.

- [ ] **Step 8: Commit**

  ```bash
  git add boardfarm3_control/openapi.py \
          unittests/control/test_openapi.py \
          unittests/control/test_proxy_path_params.py
  git commit -m "fix(openapi): move session_id from path param to request body"
  ```

---

### Task 3: Full suite verification

**Files:** none modified — verification only

- [ ] **Step 1: Run the complete unit test suite**

  ```bash
  pytest unittests/ -v
  ```

  Expected: all tests pass with no regressions in API or control tests.

- [ ] **Step 2: Run the lint suite**

  ```bash
  nox -s lint
  ```

  Expected: ruff, flake8, and mypy all pass. Common issues to watch:
  - mypy may flag `Any` annotations — ensure every use of `Any` has an `# noqa: ANN401` comment
  - ruff may flag the `import json as _json` placement — move it to the stdlib imports block if needed

- [ ] **Step 3: Fix any lint issues and re-run**

  If `nox -s lint` fails, fix the reported issues, then re-run until clean.

- [ ] **Step 4: Commit lint fixes if any**

  ```bash
  git add boardfarm3_control/openapi.py boardfarm3_control/proxy.py
  git commit -m "chore(lint): fix lint issues after session_id body param migration"
  ```

  Skip this step if there were no lint fixes needed.
