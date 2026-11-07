export default function ProgressBar({value,max=100,tone='blue'}){const pct=Math.min(100,max?value/max*100:0);return <div className={`progress-track ${tone}`}><span style={{width:`${pct}%`}}/></div>}
