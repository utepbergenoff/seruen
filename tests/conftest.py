import pytest
from fastapi.testclient import TestClient

from backend.app import create_app, scenarios
from backend.config import ROOT, Settings
from backend.schemas import RecommendRequest
from backend.service import RecommendationService
from backend.embeddings import build_index
from backend.loader import load_pois


@pytest.fixture(scope="session")
def sample_index(tmp_path_factory):
    path = tmp_path_factory.mktemp("sample_index") / "lsa.json"
    build_index(load_pois(ROOT / "data/poi_sample.json"), path)
    return path


@pytest.fixture
def settings(sample_index):
    return Settings(
        poi_path=ROOT / "data/poi_sample.json", index_path=sample_index, data_kind="sample", warm_cache=False
    )


@pytest.fixture
def service(settings):
    return RecommendationService(settings)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def request_data():
    return scenarios()[0]["request"]


@pytest.fixture
def req(request_data):
    return RecommendRequest.model_validate(request_data)
