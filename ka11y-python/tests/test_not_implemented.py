import pytest

from ka11y.utils import not_implemented


def test_not_implemented_raises_for_sync_functions():
    @not_implemented(reason="sync stub")
    def stub() -> str:
        return "never reached"

    with pytest.raises(NotImplementedError) as exc:
        stub()

    assert "sync stub" in str(exc.value)
    assert getattr(stub, "__not_implemented__", False) is True


@pytest.mark.asyncio
async def test_not_implemented_raises_for_async_functions():
    @not_implemented(reason="async stub")
    async def stub() -> str:
        return "never reached"

    with pytest.raises(NotImplementedError) as exc:
        await stub()

    assert "async stub" in str(exc.value)
    assert getattr(stub, "__not_implemented__", False) is True


def test_not_implemented_supports_bare_decorator_usage():
    @not_implemented
    def stub() -> None:
        return None

    with pytest.raises(NotImplementedError) as exc:
        stub()

    assert "is not implemented yet" in str(exc.value)
