"""验证原始消息标准化、作者过滤、版本指纹和凭证配置约束。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
import pytest
from pydantic import ValidationError

from trading.collector.messages import MessageSnapshot, normalize_message
from trading.config import Settings, Sources


def message(channel=None):
    """构造不依赖 Discord 网络的消息样本，供标准化测试使用。"""
    return SimpleNamespace(
        id=9007199254740993,
        guild=SimpleNamespace(id=10),
        channel=channel or SimpleNamespace(id=20, name="trading"),
        author=SimpleNamespace(
            id=30,
            display_name="Trader A",
            display_avatar=SimpleNamespace(url="https://cdn.discordapp.com/embed/avatars/0.png"),
        ),
        content="取消了；止损不变",
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
        edited_at=None,
        reference=SimpleNamespace(message_id=9007199254740992, channel_id=20),
        attachments=[],
        embeds=[],
        type=SimpleNamespace(value=0),
    )


def test_normalization_preserves_large_ids_original_text_and_reply():
    """验证超出 JavaScript 安全整数范围的 ID、原文和引用信息不会丢失。"""
    snapshot = normalize_message(message())
    assert snapshot.message_id == "9007199254740993"
    assert snapshot.content == "取消了；止损不变"
    assert snapshot.reply_to_message_id == "9007199254740992"
    assert snapshot.channel_id == "20"
    assert snapshot.thread_id is None
    assert snapshot.parent_channel_id is None


def test_thread_keeps_actual_channel_and_parent_separate():
    """验证 Thread 实际消息位置与父频道分别保存。"""
    channel = MagicMock(spec=discord.Thread)
    channel.name = "trading-thread"
    channel.id = 21
    channel.parent_id = 20
    snapshot = normalize_message(message(channel))
    assert snapshot.channel_id == snapshot.thread_id == "21"
    assert snapshot.parent_channel_id == "20"


def test_snapshot_fingerprint_is_stable_and_versions_differ():
    """验证相同快照指纹稳定，而内容变更产生不同版本。"""
    first = normalize_message(message())
    assert (
        first.fingerprint
        == MessageSnapshot.model_validate_json(first.model_dump_json()).fingerprint
    )
    edited = first.model_copy(update={"content": "已平仓"})
    assert first.fingerprint != edited.fingerprint


def test_source_filter_does_not_mix_authors_between_channels():
    """验证频道与作者规则必须成对匹配，不串用其他频道的作者。"""
    sources = Sources.model_validate(
        {
            "sources": [
                {"name": "a", "channel_id": "20", "author_ids": ["30"]},
                {"name": "b", "channel_id": "21", "author_ids": ["31"]},
            ]
        }
    )
    assert sources.matches("20", "30")
    assert not sources.matches("20", "31")
    assert not sources.matches("21", "30")
    assert not sources.matches("22", "30")


def test_empty_configuration_is_idle_but_empty_author_allowlist_is_rejected():
    """验证空来源列表允许空闲运行，但单个来源不能配置空作者白名单。"""
    assert not Sources.model_validate({"sources": []}).matches("20", "30")
    with pytest.raises(ValidationError):
        Sources.model_validate({"sources": [{"name": "a", "channel_id": "20", "author_ids": []}]})


def test_secrets_are_masked_and_password_special_characters_survive():
    """验证配置展示掩码凭证，且连接 URL 保留密码中的特殊字符。"""
    settings = Settings(db_password="test:@/password", discord_token="fake-secret-token")
    assert "fake-secret-token" not in repr(settings)
    assert "test:@/password" not in repr(settings)
    assert settings.database_url.password == "test:@/password"


def test_profile_metadata_is_saved_without_changing_content_fingerprint():
    """验证头像和昵称留存，但资料变更不会制造新的交易消息版本。"""
    snapshot = normalize_message(message())
    assert snapshot.author_name == "Trader A"
    assert snapshot.channel_name == "trading"
    assert snapshot.author_avatar_url == "https://cdn.discordapp.com/embed/avatars/0.png"
    changed = snapshot.model_copy(update={"author_name": "New name", "channel_name": "renamed"})
    assert changed.fingerprint == snapshot.fingerprint
