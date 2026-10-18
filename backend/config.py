import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    poi_path: Path = ROOT / "data/poi.json"
    data_kind: str = "real"
    index_path: Path = ROOT / "data/index/lsa.json"
    gemini_api_key: str = field(default="", repr=False)
    google_places_api_key: str = field(default="", repr=False)
    google_places_enabled: bool = False
    google_places_timeout_s: float = 3.0
    twogis_api_key: str = field(default="", repr=False)
    twogis_enabled: bool = False
    twogis_timeout_s: float = 5.0
    photos_enabled: bool = True
    photo_index_url: str = "https://seruen-astana.netlify.app/img/places/index.json"
    photo_timeout_s: float = 20.0
    photo_ai_per_minute: int = 8
    photo_ai_per_day: int = 400
    gemini_model: str = "gemini-3.5-flash-lite"
    ai_timeout_s: float = 8.0
    airport_reserve_min: int = 60
    cache_size: int = 256
    mock: bool = False
    warm_cache: bool = True
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000")

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        path = Path(os.getenv("POI_PATH", "data/poi.json"))
        path = path if path.is_absolute() else ROOT / path
        sample = "sample" in path.name
        return cls(
            poi_path=path,
            data_kind=os.getenv("DATA_KIND", "sample" if sample else "real"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            google_places_api_key=os.getenv("GOOGLE_PLACES_API_KEY", "") or os.getenv("GOOGLE_API_KEY", ""),
            google_places_enabled=os.getenv("GOOGLE_PLACES_ENABLED", "false").lower() == "true",
            twogis_api_key=os.getenv("TWOGIS_API_KEY", ""),
            twogis_enabled=os.getenv("TWOGIS_ENABLED", "false").lower() == "true",
            photos_enabled=os.getenv("PHOTOS_ENABLED", "true").lower() == "true",
            photo_index_url=os.getenv("PHOTO_INDEX_URL", cls.photo_index_url),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            mock=os.getenv("MOCK_MODE", "false").lower() == "true",
            warm_cache=os.getenv("WARM_CACHE", "true").lower() == "true",
            airport_reserve_min=int(os.getenv("AIRPORT_RESERVE_MIN", "60")),
            cors_origins=tuple(
                x.strip().rstrip("/")
                for x in os.getenv("CORS_ORIGINS", ",".join(cls.cors_origins)).split(",")
                if x.strip()
            ),
        )
