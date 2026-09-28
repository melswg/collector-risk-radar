import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
const apiTarget = (globalThis as {process?: {env?: Record<string,string|undefined>}}).process?.env?.API_PROXY_TARGET ?? 'http://127.0.0.1:8000';
export default defineConfig({ plugins:[react()],server:{proxy:{'/api':apiTarget}},build:{rollupOptions:{input:{main:'index.html',demo:'demo.html',alertPreview:'alert-preview.html',mapPreview:'map-preview.html'}}} });
