import {useEffect, useState} from 'react';
import {ImagePlus, Trash2, X} from 'lucide-react';
import {useModalFocus} from './useModalFocus';
import './appearance.css';

export const themes = [
  {id:'blue', name:'Московский', color:'#394d8c'},
  {id:'graphite', name:'Графит', color:'#343c4c'},
  {id:'emerald', name:'Изумруд', color:'#176b56'},
  {id:'forest', name:'Лес', color:'#356142'},
  {id:'violet', name:'Аметист', color:'#684aa1'},
  {id:'plum', name:'Слива', color:'#754667'},
  {id:'coral', name:'Коралл', color:'#a8474e'},
  {id:'terracotta', name:'Терракота', color:'#a25035'},
  {id:'amber', name:'Янтарь', color:'#876013'},
  {id:'teal', name:'Бирюза', color:'#126b76'},
] as const;

export type ThemeId = typeof themes[number]['id'];
const themeKey = 'moscollector-theme-v1';
const photoKey = 'moscollector-wallpaper-v1';

export function readTheme(): ThemeId {
  try {
    const stored = localStorage.getItem(themeKey);
    return themes.find(theme => theme.id === stored)?.id ?? 'blue';
  } catch {return 'blue';}
}

export function readPhoto(): string | null {
  try {
    const stored = localStorage.getItem(photoKey);
    return stored?.startsWith('data:image/jpeg;base64,') ? stored : null;
  } catch {return null;}
}

function compressPhoto(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, 1920 / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      const context = canvas.getContext('2d');
      if (!context) {reject(new Error('Не удалось обработать изображение.')); return;}
      context.fillStyle = '#fff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL('image/jpeg', .78));
    };
    image.onerror = () => {URL.revokeObjectURL(url); reject(new Error('Не удалось открыть изображение.'));};
    image.src = url;
  });
}

type Props = {
  theme: ThemeId;
  photo: string | null;
  onTheme: (theme: ThemeId) => void;
  onPhoto: (photo: string | null) => void;
  onClose: () => void;
};

export function AppearanceSettings({theme, photo, onTheme, onPhoto, onClose}: Props) {
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  useModalFocus(true, '.appearance-dialog');
  useEffect(() => {
    const close = (event: KeyboardEvent) => {if (event.key === 'Escape') onClose();};
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [onClose]);

  function selectTheme(next: ThemeId) {
    try {localStorage.setItem(themeKey, next); onTheme(next); setError('');}
    catch {setError('Не удалось сохранить тему в этом браузере.');}
  }

  async function selectPhoto(file?: File) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {setError('Выберите файл изображения.'); return;}
    if (file.size > 20 * 1024 * 1024) {setError('Фото должно быть меньше 20 МБ.'); return;}
    setWorking(true); setError('');
    try {
      const next = await compressPhoto(file);
      localStorage.setItem(photoKey, next);
      onPhoto(next);
    } catch {setError('Не удалось сохранить фото. Попробуйте файл меньшего размера или освободите место в браузере.');}
    finally {setWorking(false);}
  }

  function removePhoto() {
    try {localStorage.removeItem(photoKey); onPhoto(null); setError('');}
    catch {setError('Не удалось удалить фото из хранилища браузера.');}
  }

  return <div className="appearance-overlay" onClick={onClose}>
    <section className="appearance-dialog" role="dialog" aria-modal="true" aria-labelledby="appearance-title" onClick={event => event.stopPropagation()}>
      <header><div><h2 id="appearance-title">Внешний вид</h2><p>Оформление сохраняется в этом браузере.</p></div><button type="button" aria-label="Закрыть настройки внешнего вида" onClick={onClose}><X size={20}/></button></header>
      <h3>Цветовая тема</h3>
      <div className="appearance-themes" role="group" aria-label="Цветовая тема">
        {themes.map(item => <button type="button" key={item.id} aria-pressed={theme === item.id} onClick={() => selectTheme(item.id)}><span className="appearance-swatch" style={{backgroundColor:item.color}}/>{item.name}</button>)}
      </div>
      <h3>Своё фото на фон</h3>
      <div className="appearance-photo" style={photo ? {backgroundImage:`url("${photo}")`} : undefined}>
        {!photo && <span>Ваш фон появится здесь</span>}
      </div>
      <div className="appearance-actions"><label className="appearance-upload"><ImagePlus size={17}/>{working ? 'Обрабатываем…' : photo ? 'Заменить фото' : 'Выбрать фото'}<input type="file" accept="image/*" disabled={working} onChange={event => {void selectPhoto(event.target.files?.[0]); event.target.value = '';}}/></label>{photo && <button type="button" onClick={removePhoto}><Trash2 size={16}/> Убрать фото</button>}</div>
      <p className="appearance-note">Фото остаётся на этом устройстве. Карта и рабочие карточки сохраняют читаемость.</p>
      {error && <p className="appearance-error" role="alert">{error}</p>}
    </section>
  </div>;
}
