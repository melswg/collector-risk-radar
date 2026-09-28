/** Bound read requests; writes may legitimately run a long forecast job. */
export async function requestJson<T>(url: string, options: RequestInit, readTimeoutMs = 30000): Promise<T> {
  const controller = new AbortController();
  const isRead = !options.method || options.method === 'GET';
  const timer = isRead ? setTimeout(() => controller.abort(), readTimeoutMs) : undefined;
  try {
    let response: Response;
    try {response = await fetch(url, {...options, signal: controller.signal});}
    catch {
      if (controller.signal.aborted) throw new Error('Сервис долго не отвечает. Повторите загрузку данных.');
      throw new Error(isRead ? 'Нет связи с сервисом. Проверьте подключение и повторите загрузку.' : 'Связь с сервисом прервалась. Проверьте результат действия перед повторной отправкой.');
    }
    if (response.status === 204) return null as T;
    let payload;
    try {payload = await response.json();}
    catch {
      if (controller.signal.aborted) throw new Error('Сервис долго не отвечает. Повторите загрузку данных.');
      throw new Error(response.ok ? 'Сервис вернул неполный или некорректный ответ. Обновите данные.' : `Сервис недоступен (HTTP ${response.status}). Повторите загрузку позже.`);
    }
    if (!response.ok) {
      const detail = payload?.error?.message;
      throw new Error(typeof detail === 'string' && detail.trim() ? detail : `Не удалось выполнить запрос (HTTP ${response.status}).`);
    }
    return payload as T;
  } finally {if (timer !== undefined) clearTimeout(timer);}
}
