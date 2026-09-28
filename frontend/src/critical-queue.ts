type Signal = {id?: string; notificationId?: string};
export function appendCritical<T extends Signal>(queue: T[], signal: T): T[] {
  const key = signal.notificationId ?? signal.id;
  return key && queue.some(item => (item.notificationId ?? item.id) === key) ? queue : [...queue, signal];
}
