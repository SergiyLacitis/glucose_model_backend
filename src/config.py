from pydantic import BaseModel
from pydantic_settings import BaseSettings


class GeneralSettings(BaseModel):
    title: str = "Glocouse Model"
    description: str = "Model for glucose prediction"


class Settings(BaseSettings):
    general: GeneralSettings = GeneralSettings()


settings = Settings()
