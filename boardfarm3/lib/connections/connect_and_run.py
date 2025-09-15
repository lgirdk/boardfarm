"""Connect and run module."""

from time import sleep
from typing import Callable, ParamSpec, Protocol, TypeVar, runtime_checkable

from boardfarm3.exceptions import DeviceConnectionError

P = ParamSpec("P")
T = TypeVar("T")


@runtime_checkable
class RuntimeConnectable(Protocol):
    """Runtine connectable protocol class."""

    def connect_console(self) -> None:
        """Connect to the console."""

    def disconnect_console(self) -> None:
        """Disconnect from the console."""

    def is_console_connected(self) -> bool:
        """Get status of the connection."""


def connect_and_run(func: Callable[P, T]) -> Callable[P, T]:
    """Connect run and disconnect to console at runtime.

    Note: This is implemented only for instance methods

    :param func: the decorated method
    :return: True or False
    :rtype: Callable[P, T]
    """

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        instance = args[0]
        exc_to_raise = None
        conn_exception = None
        if not isinstance(instance, RuntimeConnectable):
            msg = (
                f"Provided instance {instance} do not ,"
                f"follows the protocol RuntimeConnectable .i.e {RuntimeConnectable}"
            )
            raise TypeError(msg)

        if not instance.is_console_connected():
            # Adding a retry
            for _ in range(10):
                try:
                    instance.connect_console()
                    break
                except DeviceConnectionError as exc:
                    conn_exception = exc
                    sleep(15)
            else:
                raise conn_exception

        try:
            output = func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 pylint: disable=W0718
            exc_to_raise = e
        finally:
            if instance.is_console_connected():
                instance.disconnect_console()
        if exc_to_raise:
            raise exc_to_raise
        return output

    return wrapper
