export function eventPresentation(severity: unknown) {
  const known: Record<string, {label: string; tone: string}> = {
    normal: {label: 'Норма', tone: 'normal'},
    info: {label: 'Информация', tone: 'info'},
    warning: {label: 'Предупреждение', tone: 'warning'},
    critical: {label: 'Критическое событие', tone: 'critical'},
    alarm: {label: 'Тревога', tone: 'critical'},
    error: {label: 'Ошибка', tone: 'critical'},
  };
  return typeof severity === 'string' && Object.hasOwn(known, severity)
    ? known[severity]
    : {label: 'Уровень не указан', tone: 'unknown'};
}
