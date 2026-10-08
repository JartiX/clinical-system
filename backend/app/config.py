from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://clinical:clinical@localhost:55440/clinical"
    content_dir: Path = REPO_ROOT / "content"
    # Необязательный сервер Apache Tika для DOCX/PDF, например http://localhost:9998
    tika_url: str | None = None
    default_data_class: str = "synthetic"
    # Базовый IRI для постоянных идентификаторов при выгрузке в RDF
    base_iri: str = "https://clinical-system.local/"


settings = Settings()
