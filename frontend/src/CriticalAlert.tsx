import {useEffect} from 'react';
import {ArrowUpRight, Clock3, MapPin, ShieldAlert} from 'lucide-react';
import {Row, date, incidentNames} from './api';
import './critical-alert.css';
import {useModalFocus} from './useModalFocus';

type Props = {
  prediction: Row;
  objectName: string;
  preview: boolean;
  previewHref?: string;
  onOpen: () => void;
  onLater: () => void;
};

export function CriticalAlert({prediction, objectName, preview, previewHref, onOpen, onLater}: Props) {
  useModalFocus(true,'.critical-alert');
  useEffect(() => {
    document.querySelector<HTMLElement>('.critical-alert__primary')?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onLater();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [onLater]);

  const kind = ({fire: 'Риск пожара', flood: 'Риск подтопления', sensor_failure: 'Риск отказа датчика'} as Record<string, string>)[prediction.incident_type]
    ?? `Риск: ${String(incidentNames[prediction.incident_type] ?? 'требуется проверка').toLocaleLowerCase('ru')}`;
  const score = typeof prediction.probability === 'number' ? `${Math.round(prediction.probability * 100)}%` : 'нет оценки';

  return <div className="critical-alert" role="alertdialog" aria-modal="true" aria-labelledby="critical-alert-title" aria-describedby="critical-alert-description">
    <div className="critical-alert__frame">
      <header className="critical-alert__header">
        <span className="critical-alert__brand"><span className="critical-alert__brand-mark"/> МОСКОЛЛЕКТОР / ОПЕРАТИВНЫЙ КОНТУР</span>
        <span className="critical-alert__mode">{preview ? 'ПРОСМОТР МАКЕТА' : 'НОВЫЙ КРИТИЧЕСКИЙ СИГНАЛ'}</span>
      </header>

      <div className="critical-alert__main">
        <div className="critical-alert__content">
          <div className="critical-alert__eyebrow"><ShieldAlert size={22} strokeWidth={2.5}/> КРАСНЫЙ УРОВЕНЬ / ТРЕБУЕТ ПРОВЕРКИ</div>
          <h2 id="critical-alert-title">{kind}</h2>
          <p id="critical-alert-description" className="critical-alert__lead">{objectName}</p>
          <div className="critical-alert__facts">
            <div><MapPin size={17}/><span>ОБЪЕКТ</span><strong>{objectName}</strong></div>
            <div><Clock3 size={17}/><span>ВРЕМЯ ПРОГНОЗА</span><strong>{prediction.as_of ? date(prediction.as_of) : 'Не указано'}</strong></div>
            <div><span className="critical-alert__fact-icon">%</span><span>ОЦЕНКА РИСКА</span><strong>{score}</strong></div>
          </div>
          <p className="critical-alert__qualification">Это прогноз риска, а не подтверждённая авария. Решение принимает диспетчер после проверки.</p>
          <div className="critical-alert__actions">
            {previewHref ? <a className="critical-alert__primary" href={previewHref}>Открыть объект на карте <ArrowUpRight size={22}/></a> : <button type="button" className="critical-alert__primary" onClick={onOpen}>Открыть объект на карте <ArrowUpRight size={22}/></button>}
            {previewHref ? <a className="critical-alert__secondary" href={previewHref}>Принято, проверить позже</a> : <button type="button" className="critical-alert__secondary" onClick={onLater}>Принято, проверить позже</button>}
          </div>
        </div>
      </div>

      <footer className="critical-alert__footer"><span>СИГНАЛ СОХРАНЁН В ОЧЕРЕДИ</span><span>ИСТОЧНИК: {prediction.model_kind === 'rules' ? 'ПРАВИЛА / ДЕМО' : prediction.model_kind === 'stub' ? 'STUB / ДЕМО' : prediction.model_id ? `МОДЕЛЬ ${prediction.model_id}` : 'НЕ УКАЗАН'}</span></footer>
    </div>
  </div>;
}
