import abc
import inspect


class __MetaSignatureChecker(abc.ABCMeta):
    def __init__(cls, name, bases, attrs):
        errors = []
        for base_cls in bases:
            for meth_name in getattr(base_cls, "__abstractmethods__", ()):
                if not callable(getattr(base_cls, meth_name)):
                    continue
                orig_argspec = inspect.getfullargspec(getattr(base_cls, meth_name))
                target_argspec = inspect.getfullargspec(getattr(cls, meth_name))
                if orig_argspec != target_argspec:
                    errors.append(
                        f"Abstract method {meth_name!r}  not implemented"
                        f" with correct signature in {cls.__name__!r}.\n"
                        f"Expected {orig_argspec}.\n"
                        f"Got {target_argspec}"
                    )
        if errors:
            raise TypeError("\n".join(errors))
        super().__init__(name, bases, attrs)
