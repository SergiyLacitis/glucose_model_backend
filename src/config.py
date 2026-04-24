from pydantic import BaseModel
from pydantic_settings import BaseSettings


class GeneralSettings(BaseModel):
    title: str = "Glocouse Model"
    description: str = "Model for glucose prediction"
    host: str = "0.0.0.0"
    port: int = 230
    log_level: str = "info"


class Settings(BaseSettings):
    general: GeneralSettings = GeneralSettings()


settings = Settings()
