import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.embeddings import build_index
from backend.loader import load_pois
from backend.feature_data import FeatureData

if __name__ == "__main__":
    settings = Settings.from_env()
    data = load_pois(settings.poi_path)
    FeatureData(settings.feature_data_dir, data.pois)
    dimensions = build_index(data, settings.index_path)
    print(
        f"Indexed {len(data.pois)} POIs, {dimensions} LSA dimensions; rejected={data.rejected}, duplicates={data.duplicates}"
    )
