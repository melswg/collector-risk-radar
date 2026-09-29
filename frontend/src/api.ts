import {requestJson} from './request-json';
export type Row = Record<string, any>;
export const isDemoMode = typeof window !== 'undefined' && window.location.pathname === '/demo.html';
export async function api<T = any>(path: string, body?: unknown, method?: string): Promise<T> {
  if (isDemoMode) {
    const {demoApi} = await import('./demo-api');
    return demoApi(path, body, method) as Promise<T>;
  }
  return requestJson<T>('/api/v1'+path,{credentials:'same-origin', method:method ?? (body===undefined?'GET':'POST'), headers:body instanceof FormData?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)});
}
export const incidentNames:Record<string,string>={fire:'Пожар',flood:'Подтопление',sensor_failure:'Отказ датчика',intrusion_false_alarm:'Ложная сработка',new_alarm_24h:'Новая тревожная запись в следующие 24 часа'};
export const riskNames:Record<string,string>={high:'Высокий',medium:'Повышенный',low:'Низкий',normal:'Норма',insufficient:'Недостаточно данных',unrated:'Порог не установлен'};
export const date=(v:string)=>new Date(v).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
