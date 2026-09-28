import {useEffect, useState} from 'react';
import {Monitor, Moon, Sun} from 'lucide-react';

type Preference = 'system' | 'light' | 'dark';
export function ThemeSwitcher() {
  const [preference, setPreference] = useState<Preference>(() => {
    try {
      const saved = localStorage.getItem('contour-theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch { /* System preference remains available when storage is blocked. */ }
    return 'dark';
  });
  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      document.documentElement.dataset.theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    };
    apply();
    try { localStorage.setItem('contour-theme', preference); } catch { /* The choice still applies for this session. */ }
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [preference]);
  return <div className="theme-switcher" role="group" aria-label="Тема оформления">
    {([['light', 'Светлая тема', Sun], ['dark', 'Тёмная тема', Moon], ['system', 'Как в системе', Monitor]] as const).map(([value, label, Icon]) =>
      <button type="button" key={value} aria-label={label} title={label} aria-pressed={preference === value} onClick={() => setPreference(value)}><Icon size={16}/></button>
    )}
  </div>;
}
