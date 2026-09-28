import React from 'react';
import ReactDOM from 'react-dom/client';
import {CriticalAlert} from './CriticalAlert';
import './reference-direction.css';

const example = {
  id: 'preview-critical',
  object_id: 'preview-object',
  incident_type: 'fire',
  risk: 'high',
  probability: 0.86,
  as_of: '2026-09-27T11:00:00+03:00',
  model_kind: 'rules',
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <CriticalAlert
      prediction={example}
      objectName="Демонстрационный коллектор"
      preview
      previewHref="/map-preview.html"
      onOpen={() => {window.location.href = '/map-preview.html';}}
      onLater={() => {window.location.href = '/map-preview.html';}}
    />
  </React.StrictMode>,
);
