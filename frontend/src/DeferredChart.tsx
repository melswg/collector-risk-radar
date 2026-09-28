import {Component, lazy, Suspense} from 'react';
import type {ChartProps} from './TelemetryChart';

const loadChart = () => lazy(() => import('./TelemetryChart'));

/** Keep chart loading and failures inside the reserved chart area. */
export class DeferredChart extends Component<ChartProps, {failed: boolean; Chart: ReturnType<typeof loadChart>}> {
  state = {failed: false, Chart: loadChart()};

  static getDerivedStateFromError() {return {failed: true};}

  render() {
    const {Chart, failed} = this.state;
    const height = this.props.kind === 'temperature' ? 180 : 260;
    return <div style={{height, minWidth: 0}}>
      {failed ? <div role="alert"><p>График не загрузился. Остальные сведения доступны.</p><button type="button" onClick={() => this.setState({failed: false, Chart: loadChart()})}>Повторить загрузку графика</button></div> :
        <Suspense fallback={<p role="status">Загружаем график…</p>}><Chart {...this.props}/></Suspense>}
    </div>;
  }
}
