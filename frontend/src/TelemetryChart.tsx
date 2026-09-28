import {CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {date, type Row} from './api';

export type ChartProps = {kind: 'temperature' | 'quality'; points: Row[]};

export default function TelemetryChart({kind, points}: ChartProps) {
  if (kind === 'temperature') return <ResponsiveContainer width="100%" height={180}><LineChart data={points}><CartesianGrid stroke="#dce5f3" strokeDasharray="3 3" vertical={false}/><XAxis dataKey="time" minTickGap={60} tick={{fill: '#6076a3', fontSize: 11}}/><YAxis domain={['auto', 'auto']} tick={{fill: '#6076a3', fontSize: 11}}/><Tooltip/><Line type="monotone" dataKey="value" name="Температура, °C" stroke="#40558f" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer>;
  return <ResponsiveContainer width="100%" height={260}><LineChart data={points}><CartesianGrid stroke="#d9e3f2" strokeDasharray="3 3" vertical={false}/><XAxis dataKey="as_of" tickFormatter={date} minTickGap={65} stroke="#6c7fa3"/><YAxis domain={[0,1]} width={36} stroke="#6c7fa3"/><Tooltip labelFormatter={value => date(String(value))}/><Line dataKey="probability" name="Вероятность прогноза" stroke="#40558f" strokeWidth={2} dot={false} isAnimationActive={false}/><Line dataKey="label" name="Наблюдаемый исход" stroke="#b26a38" strokeWidth={2} dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer>;
}
