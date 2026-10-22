import type { TimeBin } from "./map-data";

export function PostTimeline({ bins, since, until, frame, playing, onDates, onFrame, onPlay, onReset }: {
  bins: TimeBin[]; since: string; until: string; frame: number | null; playing: boolean;
  onDates: (since: string, until: string) => void; onFrame: (n: number) => void; onPlay: () => void; onReset: () => void;
}) {
  let peak = 1;
  for (const bin of bins) peak = Math.max(peak, bin.count);
  const throughBin = until ? bins.findIndex((b) => b.end >= until) : -1;
  const index = frame ?? (throughBin >= 0 ? throughBin : bins.length - 1);
  return <section className="post-timeline" aria-label="Post publication timeline">
    <div className="timeline-heading"><strong>Posts over time</strong><small className="muted">UTC publication dates · click a bar to isolate a period</small></div>
    <div className="timeline-controls">
      <label className="field-block"><span>From</span><input type="date" value={since} max={until || undefined} onChange={(e) => onDates(e.target.value, until)} /></label>
      <label className="field-block"><span>Through</span><input type="date" value={until} min={since || undefined} onChange={(e) => onDates(since, e.target.value)} /></label>
      <button className="button button-secondary button-small" onClick={onPlay} disabled={bins.length < 2} aria-pressed={playing}>{playing ? "Pause time" : "Play over time"}</button>
      <button className="button button-quiet button-small" onClick={onReset} disabled={!since && !until && frame === null}>All time</button>
    </div>
    {bins.length > 0 ? <>
      <div className="time-histogram" aria-label="Publication counts by period">{bins.map((b) => <button type="button" key={b.start} title={`${b.label}: ${b.count.toLocaleString()} posts`}
        aria-label={`${b.label}: ${b.count.toLocaleString()} posts`} aria-pressed={since === b.start && until === b.end}
        className={(since && b.end < since) || (until && b.start > until) ? "outside" : ""}
        onClick={() => onDates(b.start, b.end)}><i style={{ height: `${b.count ? Math.max(5, b.count / peak * 100) : 2}%`, backgroundColor: `hsl(${205 - 180 * b.count / peak} 72% 48%)` }} /></button>)}</div>
      <input className="time-scrubber" type="range" min={0} max={Math.max(0, bins.length - 1)} value={Math.max(0, index)} aria-label="Show posts through period"
        aria-valuetext={bins[Math.max(0, index)]?.label} onChange={(e) => onFrame(Number(e.target.value))} />
      <div className="timeline-range"><small>{bins[0].label}</small><small role="status">{until ? `Through ${until}` : "All dated posts"}</small><small>{bins[bins.length - 1].label}</small></div>
    </> : <p className="muted">No known publication dates to animate.</p>}
  </section>;
}
