"""Генерация зафиксированных схем из канонических моделей."""
import json
from pathlib import Path
import yaml
from backend.contracts import PredictRequest, PredictResponse, TrainJob

folder = Path('contracts/ml')
for model, filename in [(PredictRequest, 'predict_request'), (PredictResponse, 'predict_response'), (TrainJob, 'train_job')]:
    schema = model.model_json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    (folder/f'{filename}.schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2))
paths = {}
for path, methods in {'/health': ['get'], '/models': ['get'], '/predict': ['post'], '/predict/jobs': ['post'], '/predict/jobs/{id}': ['get'], '/train/jobs': ['post'], '/train/jobs/{id}': ['get'], '/models/{id}/activate': ['post'], '/models/{id}/shadow': ['post']}.items():
    paths['/v1'+path] = {}
    for method in methods:
        operation = {'summary': path, 'security': [{'serviceToken': []}], 'responses': {'200': {'description': 'Успешный ответ'}}}
        if '{id}' in path:
            operation['parameters'] = [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}]
        if method == 'post' and path in ('/predict', '/predict/jobs', '/train/jobs'):
            filename = 'train_job' if path == '/train/jobs' else 'predict_request'
            operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': {'$ref': filename+'.schema.json'}}}}
        if path == '/predict':
            operation['responses']['200']['content'] = {'application/json': {'schema': {'$ref': 'predict_response.schema.json'}}}
        paths['/v1'+path][method] = operation
spec = {'openapi': '3.1.0', 'info': {'title': 'ML Integration Contract', 'version': '1.0'}, 'paths': paths, 'components': {'securitySchemes': {'serviceToken': {'type': 'http', 'scheme': 'bearer'}}}}
(folder/'openapi.yaml').write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False))
