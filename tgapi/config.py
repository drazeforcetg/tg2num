from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    telegramApiId: int = Field(alias="TELEGRAM_API_ID")
    telegramApiHash: str = Field(alias="TELEGRAM_API_HASH")
    telegramSessionString: str = Field(alias="TELEGRAM_SESSION_STRING")
    targetBotUsername: str = Field(alias="TARGET_BOT_USERNAME")
    mongoUri: str = Field(alias="MONGO_URI")
    redisUrl: str = Field(alias="REDIS_URL")
    apiSecretSalt: str = Field(alias="API_SECRET_SALT")
    workerCount: int = Field(alias="WORKER_COUNT")
    requestTimeoutSec: int = Field(alias="REQUEST_TIMEOUT_SEC")
    rateLimitPerMinute: int = Field(alias="RATE_LIMIT_PER_MINUTE")
    adminTelegramIds: str = Field(alias="ADMIN_TELEGRAM_IDS")
    adminBotToken: str = Field(alias="ADMIN_BOT_TOKEN")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)

def getSettings():
    return Settings()