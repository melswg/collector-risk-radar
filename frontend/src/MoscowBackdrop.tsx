import {MapContainer, TileLayer} from 'react-leaflet';

/** Geographic context only. Demo tunnel nodes are deliberately not tied to this map. */
export function MoscowBackdrop() {
  return <div className="moscow-backdrop" aria-hidden="true">
    <MapContainer center={[55.7512, 37.6184]} zoom={12} zoomControl={false} attributionControl={false} dragging={false} scrollWheelZoom={false} doubleClickZoom={false} touchZoom={false} keyboard={false} style={{height: '100%', width: '100%'}}>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19}/>
    </MapContainer>
  </div>;
}
