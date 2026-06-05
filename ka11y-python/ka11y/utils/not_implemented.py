from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")


def _build_message(target: Callable[..., Any], reason: str | None) -> str:
    location = f"{target.__module__}.{target.__qualname__}"
    if reason:
        return f"{location} is not implemented yet: {reason}"
    return f"{location} is not implemented yet."


@overload
def not_implemented(func: Callable[P, R], /) -> Callable[P, R]: ...


@overload
def not_implemented(
    *, reason: str | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def not_implemented(
    func: Callable[P, R] | None = None,
    /,
    *,
    reason: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]] | Callable[P, R]:
    """
    Decorate a function or coroutine function as intentionally unavailable.

    The wrapped callable preserves its original metadata and raises a
    ``NotImplementedError`` with a stable, fully-qualified message whenever it
    is called.
    """

    def decorator(target: Callable[P, R]) -> Callable[P, R]:
        message = _build_message(target, reason)

        if inspect.iscoroutinefunction(target):

            @wraps(target)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                raise NotImplementedError(message)

            setattr(async_wrapper, "__not_implemented__", True)
            setattr(async_wrapper, "__not_implemented_reason__", reason)
            return async_wrapper

        @wraps(target)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            raise NotImplementedError(message)

        setattr(wrapper, "__not_implemented__", True)
        setattr(wrapper, "__not_implemented_reason__", reason)
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
