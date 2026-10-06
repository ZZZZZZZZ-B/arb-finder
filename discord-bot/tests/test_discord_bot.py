from __future__ import annotations

TARGET_CHANNEL_ID = 123456789

import pytest

from discord_bot import (
    build_payload,
    image_data_url,
    normalize_tf,
    parse_decision,
    request_answer,
    BotSettings,
    OPENROUTER_URL,
)


def test_build_payload_includes_question_and_image() -> None:
    payload = build_payload("test/model", "Is this true?", "data:image/png;base64,abc")

    assert payload["model"] == "test/model"
    assert "messages" not in payload
    assert payload["questions"]["is_true"]["type"] == "choice"
    assert set(payload["questions"]["is_true"]["criteria"]) == {"True", "False", "unknown"}
    content = payload["state"]
    assert content[0] == {"type": "text", "text": "Is this true?"}
    assert content[1]["image_url"]["url"] == "data:image/png;base64,abc"


@pytest.mark.parametrize("choice", ["True", "False"])
def test_parse_decision(choice) -> None:
    assert parse_decision({"answers": {"is_true": {"type": "choice", "choice": choice}}}) == choice


@pytest.mark.parametrize("body", [
    {}, {"answers": {}},
    {"answers": {"is_true": {"type": "noul", "noul": 0.9}}},
    {"answers": {"is_true": {"type": "choice", "choice": "unknown"}}},
])
def test_parse_decision_rejects_invalid_or_unknown(body) -> None:
    with pytest.raises((RuntimeError, ValueError)):
        parse_decision(body)


def test_request_uses_decisions_endpoint(monkeypatch) -> None:
    from unittest.mock import MagicMock
    response = MagicMock(ok=True)
    response.json.return_value = {"answers": {"is_true": {"type": "choice", "choice": "False"}}}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("discord_bot.requests.post", post)
    payload = build_payload("test/model", "", "data:image/png;base64,abc")
    assert request_answer(BotSettings("test", "secret", TARGET_CHANNEL_ID), payload) == "False"
    assert OPENROUTER_URL == "https://openrouter.ai/api/alpha/decisions"
    assert post.call_args.args == (OPENROUTER_URL,)
    assert post.call_args.kwargs["json"] == payload


def test_sqlite_stats_persist_and_aggregate(tmp_path) -> None:
    from discord_bot import RequestStats
    path = tmp_path / "stats.sqlite3"
    stats = RequestStats(path)
    assert "总次数：0" in stats.render()
    stats.record(1.0, 0.001, False)
    stats.record(3.0, None, True)
    report = RequestStats(path).render()
    assert "总次数：2（失败：1）" in report
    assert "平均耗时：2.000 秒" in report
    assert "$0.0010000 USD" in report
    assert len(report.splitlines()) == 4


def test_request_records_cost_even_if_decision_unknown(monkeypatch, tmp_path) -> None:
    from discord_bot import RequestStats
    from unittest.mock import MagicMock
    stats = RequestStats(tmp_path / "stats.sqlite3")
    response = MagicMock(ok=True)
    response.json.return_value = {
        "answers": {"is_true": {"type": "choice", "choice": "unknown"}},
        "usage": {"cost": 0.002},
    }
    monkeypatch.setattr("discord_bot.requests.post", MagicMock(return_value=response))
    with pytest.raises(ValueError):
        request_answer(BotSettings("test", "secret", TARGET_CHANNEL_ID), {}, stats)
    assert "总次数：1（失败：1）" in stats.render()
    assert "$0.0020000 USD" in stats.render()


def test_request_records_network_failure(monkeypatch, tmp_path) -> None:
    import requests
    from unittest.mock import MagicMock
    from discord_bot import RequestStats
    stats = RequestStats(tmp_path / "stats.sqlite3")
    monkeypatch.setattr("discord_bot.requests.post", MagicMock(side_effect=requests.Timeout))
    with pytest.raises(requests.Timeout):
        request_answer(BotSettings("test", "secret", TARGET_CHANNEL_ID), {}, stats)
    assert "总次数：1（失败：1）" in stats.render()
    connection = stats.connect()
    try:
        assert connection.execute("SELECT cost_usd FROM api_requests").fetchone()[0] is None
    finally:
        connection.close()


def test_stats_command_channel_guard_and_response(monkeypatch, tmp_path) -> None:
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from discord_bot import TrueFalseClient
    monkeypatch.setenv("DISCORD_STATS_DB", str(tmp_path / "stats.sqlite3"))
    client = TrueFalseClient(BotSettings("test", "secret", TARGET_CHANNEL_ID))
    interaction = SimpleNamespace(
        channel_id=TARGET_CHANNEL_ID + 1,
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    async def exercise():
        await client.show_stats(interaction)
        interaction.response.send_message.assert_awaited_once()
        interaction.response.defer.assert_not_awaited()
        interaction.channel_id = TARGET_CHANNEL_ID
        await client.show_stats(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        assert "总次数：0" in interaction.followup.send.call_args.args[0]
        assert client.tree.get_command("stats") is not None
        await client.close()
    asyncio.run(exercise())


def test_image_data_url_encodes_bytes() -> None:
    assert image_data_url(b"png", "shot.png", None) == "data:image/png;base64,cG5n"


@pytest.mark.parametrize("value, expected", [("T", "True"), ("True", "True"), ("False", "False"), (" f ", "False") ])
def test_normalize_tf(value: str, expected: str) -> None:
    assert normalize_tf(value) == expected


@pytest.mark.parametrize("value", ["Unable to decide", "T or F", "True or False"])
def test_normalize_tf_rejects_ambiguous_output(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_tf(value)


def test_message_handler_filters_channel_and_answers_image(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DISCORD_STATS_DB", str(tmp_path / "stats.sqlite3"))
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from discord_bot import BotSettings, TrueFalseClient

    attachment = SimpleNamespace(
        content_type="image/png", filename="shot.png", size=3,
        read=AsyncMock(return_value=b"png"),
    )
    typing = MagicMock()
    typing.__aenter__ = AsyncMock()
    typing.__aexit__ = AsyncMock(return_value=False)
    message = SimpleNamespace(
        channel=SimpleNamespace(id=TARGET_CHANNEL_ID + 1, typing=lambda: typing),
        author=SimpleNamespace(bot=False), attachments=[attachment],
        content="", reply=AsyncMock(),
    )
    request = MagicMock(return_value="True")
    monkeypatch.setattr("discord_bot.request_answer", request)
    client = TrueFalseClient(BotSettings("test", "test", TARGET_CHANNEL_ID))

    async def exercise():
        await client.on_message(message)
        attachment.read.assert_not_awaited()
        request.assert_not_called()
        message.channel.id = TARGET_CHANNEL_ID
        message.attachments = []
        await client.on_message(message)
        request.assert_not_called()
        message.attachments = [attachment]
        await client.on_message(message)
        message.reply.assert_awaited_once_with("True", mention_author=False)
        await client.close()

    asyncio.run(exercise())
