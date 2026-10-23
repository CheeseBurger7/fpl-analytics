import httpx
import pytest

from fpl.api import FPLAPIError


def test_retries_on_5xx_then_succeeds(make_client):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    assert make_client(handler).bootstrap_static() == {"ok": True}
    assert len(calls) == 3


def test_does_not_retry_4xx(make_client):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(FPLAPIError, match="404"):
        make_client(handler).element_summary(1)
    assert len(calls) == 1


def test_gives_up_after_retries(make_client):
    with pytest.raises(FPLAPIError, match="failed after 3"):
        make_client(lambda r: httpx.Response(500), retries=2).fixtures()


def test_retries_transport_errors(make_client):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=[])

    assert make_client(handler).fixtures() == []
