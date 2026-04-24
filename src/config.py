from pydantic import BaseModel
from pydantic_settings import BaseSettings


class GeneralSettings(BaseModel):
    title: str = "Glocouse Model"
    description: str = "Model for glucose prediction"
    host: str = "0.0.0.0"
    port: int = 230
    log_level: str = "info"


class DatabaseSettings(BaseModel):
    drivername: str = "postgresql+asyncpg"
    username: str = "myuser"
    password: str = "mypassword"
    host: str = "db"
    port: int = 5432
    database_name: str = "glucosedb"
    echo: bool = False
    echo_pool: bool = False
    pool_size: int = 50
    max_overflow: int = 10


class AuthSettings(BaseModel):
    secret_key: str = "your-super-secret-key-change-it-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


class Settings(BaseSettings):
    general: GeneralSettings = GeneralSettings()
    database: DatabaseSettings = DatabaseSettings()
    auth: AuthSettings = AuthSettings()


settings = Settings()
