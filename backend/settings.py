"""Конфигурация без секретов в исходниках."""
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('DATA_DIR', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA / "app.db"}')

def config(name: str) -> dict:
    return yaml.safe_load((ROOT / 'config' / f'{name}.yaml').read_text())
