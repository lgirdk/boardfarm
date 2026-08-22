"""Docs-only response schemas on natively generated routes."""

from __future__ import annotations

import types as _types
from abc import ABC, abstractmethod

from fastapi import FastAPI
from fastapi.testclient import TestClient

from boardfarm3.api.routers._generator import generate_template_routers
from boardfarm3.api.routers._usecase_generator import generate_usecase_routers
from boardfarm3.api.routers.adapter import DefaultAdapter


class _Widget(ABC):
    """Template ABC for docs tests."""

    @abstractmethod
    def poke(self, label: str) -> bool:
        """Poke.

        :param label: what
        :type label: str
        :return: outcome
        :rtype: bool
        """


class _SyncOnlyAdapter(DefaultAdapter):
    """Non-default adapter: docs must not be attached."""

    supports_async = False


def _openapi(routers: list) -> dict:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return TestClient(app).get("/openapi.json").json()


def _uc_module() -> _types.ModuleType:
    mod = _types.ModuleType("fake_uc_docs")

    def frob(host: str) -> str:
        """Frob a host.

        :param host: target
        :type host: str
        :return: message
        :rtype: str
        """
        return host

    frob.__module__ = "fake_uc_docs"
    mod.frob = frob  # type: ignore[attr-defined]
    return mod


def test_native_template_route_documents_result_and_ticket() -> None:
    routers, _ = generate_template_routers([_Widget])
    spec = _openapi(routers)
    path = f"/templates/{_Widget.__name__.lower()}/poke"
    op = spec["paths"][path]["post"]
    r200 = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    props = spec["components"]["schemas"][r200.rsplit("/", 1)[-1]]["properties"]
    assert props["result"]["type"] == "boolean"
    assert "202" in op["responses"]
    r202 = op["responses"]["202"]["content"]["application/json"]["schema"]["$ref"]
    assert sorted(
        spec["components"]["schemas"][r202.rsplit("/", 1)[-1]]["properties"]
    ) == ["job_id", "state"]


def test_native_usecase_route_documents_result() -> None:
    routers, _ = generate_usecase_routers([_uc_module()])
    spec = _openapi(routers)
    op = spec["paths"]["/use_cases/fake_uc_docs/frob"]["post"]
    r200 = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    props = spec["components"]["schemas"][r200.rsplit("/", 1)[-1]]["properties"]
    assert props["result"]["type"] == "string"


def test_custom_adapter_routes_get_no_native_docs() -> None:
    routers, _ = generate_template_routers([_Widget], adapter=_SyncOnlyAdapter())
    spec = _openapi(routers)
    path = f"/templates/{_Widget.__name__.lower()}/poke"
    op = spec["paths"][path]["post"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {}
    assert "202" not in op["responses"]
