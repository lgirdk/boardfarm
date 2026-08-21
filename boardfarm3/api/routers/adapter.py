"""Response adapter seam for boardfarm API route generation.

A :class:`ResponseAdapter` lets a plugin reuse the core route generators while
supplying its own request-model shape, parameter coercion and response body.
:class:`DefaultAdapter` reproduces the native boardfarm contract exactly and is
used whenever no adapter is supplied, so behaviour is unchanged by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from boardfarm3.api.routers import _async_response

if TYPE_CHECKING:
    from boardfarm3.api.execution import Job


@dataclass(frozen=True)
class Unsupported:
    """Marker meaning a parameter cannot be exposed on this adapter's surface.

    Returned from :meth:`ResponseAdapter.field_spec_for`.  The generator turns
    it into a ``SkippedMethod`` carrying *reason*, so the whole method is
    excluded and reported by ``GET /diagnostics/skipped-routes``.

    :param reason: human-readable explanation recorded on the skip
    :type reason: str
    """

    reason: str


@dataclass
class Outcome:
    """The result of attempting one dispatched call.

    :param job: submitted job, or None when the call failed before submission
    :type job: Job | None
    :param value: the job's result on success; None on failure or async
    :type value: Any
    :param error: the exception raised, or None on success
    :type error: Exception | None
    :param mode: the effective dispatch mode, ``"sync"`` or ``"async"``
    :type mode: str
    """

    job: Job | None
    value: Any
    error: Exception | None
    mode: str


class ResponseAdapter(Protocol):
    """Customisation points a plugin may override for its own route surface."""

    supports_async: bool

    def field_spec_for(
        self,
        name: str,
        annotation: Any,  # noqa: ANN401
        default: Any,  # noqa: ANN401
    ) -> tuple[Any, Any] | Unsupported:
        """Return the ``(field_type, default)`` pair for one request-model field.

        :param name: parameter name
        :type name: str
        :param annotation: the parameter's Python type annotation
        :type annotation: Any
        :param default: the parameter's default, or ``...`` when required
        :type default: Any
        :return: the Pydantic field spec, or Unsupported to skip the method
        :rtype: tuple[Any, Any] | Unsupported
        """

    def coerce(
        self,
        value: Any,  # noqa: ANN401
        annotation: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Convert a decoded JSON value back to its Python type before dispatch.

        :param value: the JSON-decoded value
        :type value: Any
        :param annotation: the original Python type annotation
        :type annotation: Any
        :return: the coerced value
        :rtype: Any
        """

    def extra_fields(self) -> dict[str, tuple[Any, Any]]:
        """Return additional fields merged into every generated request model.

        These fields are stripped from the payload before dispatch, so the
        target callable never sees them.

        :return: mapping of field name to ``(type, default)``
        :rtype: dict[str, tuple[Any, Any]]
        """

    def check_request(
        self,
        body: Any,  # noqa: ANN401
        required: frozenset[str],
    ) -> Any | None:  # noqa: ANN401
        """Validate the parsed body before dispatch.

        :param body: the parsed Pydantic request model instance
        :type body: Any
        :param required: names of parameters that had no default
        :type required: frozenset[str]
        :return: a response to short-circuit with, or None to proceed
        :rtype: Any | None
        """

    def respond(self, outcome: Outcome) -> Any:  # noqa: ANN401
        """Build the HTTP response for a completed or failed call.

        :param outcome: the result of the dispatch attempt
        :type outcome: Outcome
        :return: a response body or Response object
        :rtype: Any
        """


class DefaultAdapter:
    """Reproduces the native boardfarm response contract exactly."""

    supports_async = True

    def field_spec_for(
        self,
        name: str,  # noqa: ARG002
        annotation: Any,  # noqa: ANN401
        default: Any,  # noqa: ANN401
    ) -> tuple[Any, Any] | Unsupported:
        """Substitute API-friendly types, preserving the original default.

        :param name: parameter name (unused)
        :type name: str
        :param annotation: the parameter's Python type annotation
        :type annotation: Any
        :param default: the parameter's default, or ``...`` when required
        :type default: Any
        :return: the Pydantic field spec; never Unsupported
        :rtype: tuple[Any, Any] | Unsupported
        """
        # Imported here rather than at module scope: _generator imports this
        # module for its default argument, so a top-level import would cycle.
        from boardfarm3.api.routers._generator import (  # pylint: disable=import-outside-toplevel
            _annotation_to_field_type,
        )

        return (_annotation_to_field_type(annotation), default)

    def coerce(
        self,
        value: Any,  # noqa: ANN401
        annotation: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Delegate to the shared coercion helper.

        :param value: the JSON-decoded value
        :type value: Any
        :param annotation: the original Python type annotation
        :type annotation: Any
        :return: the coerced value
        :rtype: Any
        """
        from boardfarm3.api.routers._generator import (  # pylint: disable=import-outside-toplevel
            _coerce,
        )

        return _coerce(value, annotation)

    def extra_fields(self) -> dict[str, tuple[Any, Any]]:
        """Add no fields.

        :return: an empty mapping
        :rtype: dict[str, tuple[Any, Any]]
        """
        return {}

    def check_request(
        self,
        body: Any,  # noqa: ANN401, ARG002
        required: frozenset[str],  # noqa: ARG002
    ) -> Any | None:  # noqa: ANN401
        """Never short-circuit; Pydantic already enforced required fields.

        :param body: the parsed request model (unused)
        :type body: Any
        :param required: required parameter names (unused)
        :type required: frozenset[str]
        :return: None
        :rtype: Any | None
        """
        return None

    def respond(self, outcome: Outcome) -> Any:  # noqa: ANN401
        """Re-raise failures, or return the native success body.

        Re-raising is what keeps the native path unchanged: the exception
        reaches the app-level handlers with its traceback intact.

        :param outcome: the result of the dispatch attempt
        :type outcome: Outcome
        :return: the 202 job ticket for async, else ``{"result": value}``
        :rtype: Any
        :raises Exception: whatever the dispatched call raised
        """
        if outcome.error is not None:
            raise outcome.error
        if outcome.mode == "async":
            return _async_response(outcome.job)  # type: ignore[arg-type]
        return {"result": outcome.value}
