export type Row = Record<string, any>;
export async function api<T = any>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch('/api/v1'+path,{credentials:'same-origin', method:method ?? (body===undefined?'GET':'POST'), headers:body instanceof FormData?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)});
  if(!response.ok){const err=await response.json();throw new Error(err.error?.message ?? 'Ошибка запроса');}
  return response.json();
}
export const incidentNames:Record<string,string>={fire:'Пожар',flood:'Подтопление',sensor_failure:'Отказ датчика',intrusion_false_alarm:'Ложная сработка'};
export const riskNames:Record<string,string>={high:'Высокий',medium:'Повышенный',low:'Низкий',normal:'Норма',insufficient:'Недостаточно данных'};
export const date=(v:string)=>new Date(v).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
