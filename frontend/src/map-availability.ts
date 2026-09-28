import type {Map} from 'maplibre-gl';

// A tile error must not permanently cover a map that subsequently recovered.
export function watchMapAvailability(map: Map, onError: (failed: boolean) => void, timeoutMs = 15000) {
  let active = true;
  const timer = setTimeout(() => {if (active && !map.loaded()) onError(true);}, timeoutMs);
  const fail = () => {if (active) onError(true);};
  const recover = () => {
    if (active && map.loaded()) {
      clearTimeout(timer);
      onError(false);
    }
  };
  map.on('error', fail);
  map.on('idle', recover);
  return () => {
    active = false;
    clearTimeout(timer);
    map.off('error', fail);
    map.off('idle', recover);
  };
}
