"""
ka11y.queue — message wire format and the SQS wrapper, against moto's
in-process SQS. No network, no AWS account.
"""

from __future__ import annotations

import json

import pytest

from ka11y.api.v1.combined.models import CombinedRequest
from ka11y.queue import messages as msgs
from ka11y.queue.messages import AuditJobMessage
from ka11y.queue.sqs import SQSClient, SQSNotConfigured, get_client, reset_client, settings


@pytest.fixture
def sqs_env(monkeypatch):
    moto = pytest.importorskip("moto")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("SQS_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("SQS_VISIBILITY_TIMEOUT", "30")
    monkeypatch.setenv("SQS_WAIT_TIME_SECONDS", "0")
    reset_client()
    with moto.mock_aws():
        import boto3

        url = boto3.client("sqs", region_name="us-east-1").create_queue(QueueName="ka11y-test")["QueueUrl"]
        monkeypatch.setenv("SQS_QUEUE_URL", url)
        reset_client()
        yield url
    reset_client()


def _message(job_id: str = "11111111-1111-1111-1111-111111111111") -> AuditJobMessage:
    return AuditJobMessage.for_request(job_id, CombinedRequest(url="https://example.com", lang="en"))


# ── messages ─────────────────────────────────────────────────────────────────


class TestAuditJobMessage:
    def test_roundtrip(self):
        m = _message()
        back = AuditJobMessage.from_json(m.to_json())
        assert back == m
        assert back.request().lang == "en"
        assert str(back.request().url) == "https://example.com/"

    def test_is_small(self):
        assert len(_message().to_json()) < 600, "job state belongs in object storage, not the queue"

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            AuditJobMessage.from_json("not json")
        with pytest.raises(ValueError):
            AuditJobMessage.from_json("[1, 2]")
        with pytest.raises(ValueError):
            AuditJobMessage.from_json(json.dumps({"job_id": "x"}))  # url/payload missing

    def test_rejects_other_versions(self):
        body = json.loads(_message().to_json())
        body["version"] = msgs.MESSAGE_VERSION + 1
        with pytest.raises(ValueError):
            AuditJobMessage.from_json(json.dumps(body))

    def test_bad_payload_surfaces_on_request(self):
        m = _message()
        m.payload["max_depth"] = 9  # not an allowed crawl depth
        AuditJobMessage.from_json(m.to_json())  # the envelope is still valid…
        with pytest.raises(Exception):
            m.request()  # …but it cannot become an audit request


# ── settings ─────────────────────────────────────────────────────────────────


class TestSettings:
    def test_defaults(self, monkeypatch):
        for k in ("SQS_QUEUE_URL", "SQS_ENDPOINT_URL", "SQS_VISIBILITY_TIMEOUT", "SQS_WAIT_TIME_SECONDS"):
            monkeypatch.delenv(k, raising=False)
        cfg = settings()
        assert not cfg.configured
        assert cfg.visibility_timeout == 300
        assert cfg.wait_time_seconds == 20

    def test_wait_time_is_clamped_to_sqs_limit(self, monkeypatch):
        monkeypatch.setenv("SQS_WAIT_TIME_SECONDS", "99")
        assert settings().wait_time_seconds == 20

    def test_unconfigured_client_refuses_to_send(self, monkeypatch):
        monkeypatch.delenv("SQS_QUEUE_URL", raising=False)
        reset_client()
        with pytest.raises(SQSNotConfigured):
            import asyncio

            asyncio.run(get_client().send_message(_message()))
        reset_client()


# ── client against moto ──────────────────────────────────────────────────────


class TestSQSClient:
    async def test_send_receive_delete(self, sqs_env):
        client = get_client()
        assert isinstance(client, SQSClient) and client.configured
        mid = await client.send_message(_message())
        assert mid

        got = await client.receive_messages(max_messages=5, wait_time=0)
        assert len(got) == 1
        rm = got[0]
        assert rm.receive_count == 1
        assert rm.parse().job_id == _message().job_id

        await client.delete_message(rm.receipt_handle)
        assert await client.receive_messages(max_messages=1, wait_time=0) == []
        counts = await client.approximate_counts()
        assert counts == {"visible": 0, "in_flight": 0, "delayed": 0}

    async def test_change_visibility_re_exposes_message(self, sqs_env):
        client = get_client()
        await client.send_message(_message())
        first = (await client.receive_messages(wait_time=0))[0]
        # Hidden for 30 s by the receive; nothing to see right now.
        assert await client.receive_messages(wait_time=0) == []
        await client.change_visibility(first.receipt_handle, 0)
        again = await client.receive_messages(wait_time=0)
        assert len(again) == 1
        assert again[0].receive_count == 2, "SQS counts every delivery"

    async def test_receive_batch_is_capped_at_free_slots(self, sqs_env):
        client = get_client()
        for i in range(5):
            await client.send_message(_message(f"00000000-0000-0000-0000-00000000000{i}"))
        got = await client.receive_messages(max_messages=2, wait_time=0)
        assert len(got) <= 2
