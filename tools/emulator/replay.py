"""Ускоренное воспроизведение файла СМВУ через внутренний ingestion API."""
import argparse
import os
import time
import httpx
import pandas as pd

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--speed', type=float, default=60)
    p.add_argument('--file', default='data/synthetic-small/events.parquet')
    args = p.parse_args()
    with httpx.Client(base_url=os.getenv('API_URL', 'http://localhost:8000'), timeout=60) as client:
        response = client.post('/api/v1/auth/login', json={'username': 'analyst', 'password': os.environ['DEMO_PASSWORD']})
        response.raise_for_status()
        client.headers['Authorization'] = 'Bearer '+response.json()['access_token']
        rows = pd.read_parquet(args.file).sort_values('ts').to_dict('records')
        for i in range(0, len(rows), 100):
            response = client.post('/api/v1/ingest/events', json=rows[i:i+100])
            response.raise_for_status()
            print(response.json())
            time.sleep(min(5, 300/max(args.speed, 1)))
