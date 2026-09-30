"""环境变量、Discord ID 和作者过滤契约；凭证仅在连接边界解封。"""

from typing import Annotated

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

Snowflake = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]


class Source(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1)
    channel_id: Snowflake
    author_ids: list[Snowflake] = Field(min_length=1)


class Sources(BaseModel):
    model_config = {"extra": "forbid"}
    sources: list[Source] = Field(default_factory=list)

    def matches(self, channel_id: str, author_id: str) -> bool:
        """判断频道与作者是否同时命中同一条来源规则，避免跨频道混用作者白名单。"""
        return any(s.channel_id == channel_id and author_id in s.author_ids for s in self.sources)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    db_host: str = "postgres"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_user: str = "trading"
    db_password: SecretStr = SecretStr("local-development-only")
    db_name: str = "trading"
    discord_token: SecretStr = SecretStr("")
    log_level: str = "INFO"
    r2_account_id: str = Field(default="", pattern=r"^(?:[a-fA-F0-9]{32})?$")
    r2_bucket: str = Field(default="", pattern=r"^(?:[a-z0-9][a-z0-9.-]{1,61}[a-z0-9])?$")
    r2_access_key_id: SecretStr = SecretStr("")
    r2_secret_access_key: SecretStr = SecretStr("")
    media_warning_bytes: int = Field(default=8_000_000_000, ge=1)
    media_max_image_bytes: int = Field(default=25_000_000, ge=1, le=100_000_000)
    message_freshness_seconds: int = Field(default=120, ge=1, le=86400)

    @property
    def r2_configured(self) -> bool:
        """只确认必要字段齐全，不把已填配置误报为远端连接成功。"""
        return bool(
            self.r2_account_id
            and self.r2_bucket
            and self.r2_access_key_id.get_secret_value().strip()
            and self.r2_secret_access_key.get_secret_value().strip()
        )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """统一日志级别并拒绝调试级别，降低第三方库记录敏感载荷的风险。"""
        value = value.upper()
        if value not in {"INFO", "WARNING", "ERROR"}:
            raise ValueError("LOG_LEVEL must be INFO, WARNING or ERROR")
        return value

    @property
    def database_url(self) -> URL:
        """构造 asyncpg 连接 URL；由 SQLAlchemy 处理密码中特殊字符的编码。"""
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
