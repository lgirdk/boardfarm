"""Boardfarm decorators module."""

from collections.abc import Callable
from typing import Any, TypeVar

AnyClass = TypeVar("AnyClass")


def singleton(cls: type[AnyClass]) -> Callable[..., AnyClass]:
    """Allow a class to become a decorator.

    :param cls: class to become a decorator
    :return: callable[...,AnyClass]
    """
    instances: dict[type[AnyClass], AnyClass] = {}

    def getinstance(*args: tuple, **kwargs: Any) -> AnyClass:  # noqa: ANN401
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)

        return instances[cls]

    return getinstance  # type: ignore[return-value]
