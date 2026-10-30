// Gráficos SVG próprios (portados do painel original): barras+linhas com crosshair,
// barras empilhadas, barras horizontais clicáveis, KPI e variação contra o período anterior.
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { f1, fN, pct } from "./fmt";
import { hideTip, showTip, tipProps, TipRow } from "./tip";

const niceMax = (v: number) => {
  if (v <= 0) return 4;
  const raw = v / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p * 4;
};

function useLargura<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export type Serie = { name: string; color: string; ys: (number | null)[]; tf?: (v: number | null) => string; dash?: string };
type XYProps = {
  labels: string[]; tips?: string[]; bars?: Serie[]; lines?: Serie[]; partial?: Set<number>; sel?: Set<number> | null;
  yfmt?: (v: number) => string; h?: number; lw?: number; extra?: (i: number) => ReactNode; onClick?: (i: number) => void; aria?: string;
};

/** Contêiner que mede a largura disponível; o desenho só acontece com dados. */
function Medido({ vazio, children }: { vazio: boolean; children: (w: number) => ReactNode }) {
  const [ref, w] = useLargura<HTMLDivElement>();
  return <div className="xy" ref={ref}>{vazio ? <div className="empty">Sem dados no recorte atual.</div> : children(w)}</div>;
}

export const XY = (p: XYProps) => <Medido vazio={!p.labels.length}>{w => <XYSvg {...p} W={w} />}</Medido>;

function XYSvg({ labels, tips, bars = [], lines = [], partial, sel, yfmt = fN, h: H = 230, lw = 52, extra, onClick, aria, W }: XYProps & { W: number }) {
  const [cx, setCx] = useState<number | null>(null);
  const n = labels.length;
  const m = { l: 46, r: 10, t: 10, b: 26 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
  const all = [...bars, ...lines].flatMap(s => s.ys.filter((v): v is number => v != null));
  const max = niceMax(Math.max(...all, 1)), band = iw / n;
  const X = (i: number) => m.l + band * (i + .5), Y = (v: number) => m.t + ih - v / max * ih;
  const nb = bars.length, bw = Math.max(1.2, Math.min(34, band * .72 / Math.max(nb, 1)));
  const every = Math.ceil(n / Math.max(2, Math.floor(iw / lw)));
  const idx = (e: React.MouseEvent<SVGRectElement>) =>
    Math.max(0, Math.min(n - 1, Math.floor((e.clientX - e.currentTarget.getBoundingClientRect().left) / (iw / n))));
  const mover = (e: React.MouseEvent<SVGRectElement>) => {
    const i = idx(e); setCx(i);
    showTip(<><b>{tips?.[i] ?? labels[i]}</b>
      {[...bars, ...lines].map(s => <TipRow key={s.name} cor={s.color} nome={s.name} valor={(s.tf || yfmt as any)(s.ys[i])} />)}
      {extra?.(i)}{onClick && <div style={{ opacity: .7, marginTop: 4 }}>clique para detalhar</div>}</>, e);
  };
  return (
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={aria}>
        {[0, 1, 2, 3, 4].map(k => { const v = max * k / 4, y = Y(v); return <g key={k}><line className="ax" x1={m.l} x2={W - m.r} y1={y} y2={y} /><text x={m.l - 6} y={y + 4} textAnchor="end">{yfmt(v)}</text></g>; })}
        {bars.map((b, bi) => b.ys.map((v, i) => {
          if (v == null) return null;
          const h = Math.max(0, v / max * ih), x = X(i) - bw * nb / 2 + bw * bi, part = partial?.has(i);
          return <rect key={`${bi}-${i}`} x={x} y={m.t + ih - h} width={bw} height={h} rx={bw > 6 ? 3 : 0} fill={b.color}
            opacity={part ? .5 : sel && !sel.has(i) ? .38 : 1} {...(part ? { stroke: b.color, strokeDasharray: "3 2" } : {})} />;
        }))}
        {lines.map(l => {
          let d = "", pen = false;
          l.ys.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; });
          return <g key={l.name}><path d={d} fill="none" stroke={l.color} strokeWidth={2} strokeLinejoin="round" strokeDasharray={l.dash} />
            {n <= 24 && l.ys.map((v, i) => v != null && <circle key={i} cx={X(i)} cy={Y(v)} r={3.5} fill={l.color} stroke="var(--surface)" strokeWidth={2} />)}</g>;
        })}
        {labels.map((t, i) => i % every === 0 && <text key={i} x={X(i)} y={H - 8} textAnchor="middle">{t}</text>)}
        {cx != null && <line className="ax" stroke="var(--ink-3)" x1={X(cx)} x2={X(cx)} y1={m.t} y2={m.t + ih} />}
        <rect x={m.l} y={m.t} width={iw} height={ih} fill="transparent" style={{ cursor: onClick ? "pointer" : "default" }}
          onMouseMove={mover} onMouseLeave={() => { setCx(null); hideTip(); }} onClick={e => onClick?.(idx(e))} />
      </svg>
  );
}

type StackProps = { labels: string[]; series: Serie[]; partial?: number; onClick?: (i: number) => void; fmtSerie?: (s: string) => string };
export const Stack = (p: StackProps) => <Medido vazio={!p.labels.length}>{w => <StackSvg {...p} W={w} />}</Medido>;

function StackSvg({ labels, series, partial, onClick, fmtSerie = s => s, W }: StackProps & { W: number }) {
  const H = 250, m = { l: 46, r: 10, t: 10, b: 26 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
  const tot = labels.map((_, i) => series.reduce((t, s) => t + (s.ys[i] || 0), 0));
  const max = niceMax(Math.max(...tot, 1)), band = iw / labels.length, bw = Math.min(46, band * .7);
  return (
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
        {[0, 1, 2, 3, 4].map(k => { const v = max * k / 4, y = m.t + ih - v / max * ih; return <g key={k}><line className="ax" x1={m.l} x2={W - m.r} y1={y} y2={y} /><text x={m.l - 6} y={y + 4} textAnchor="end">{fN(v)}</text></g>; })}
        {labels.map((lb, i) => {
          let acc = 0; const x = m.l + band * (i + .5) - bw / 2;
          const tip = <><b>{lb}</b>{[...series].reverse().filter(s => s.ys[i]).map(s => <TipRow key={s.name} cor={s.color} nome={fmtSerie(s.name)} valor={fN(s.ys[i])} />)}
            <div className="r" style={{ marginTop: 3, borderTop: "1px solid rgba(255,255,255,.25)", paddingTop: 3 }}><span>Total</span><b style={{ display: "inline" }}>{fN(tot[i])}</b></div></>;
          return <g key={lb}>
            {series.map(s => {
              const v = s.ys[i]; if (!v) return null; const h = v / max * ih; acc += h;
              return <rect key={s.name} x={x} y={m.t + ih - acc} width={bw} height={Math.max(h, 0)} fill={s.color} stroke="var(--surface)" strokeWidth={1.5}
                opacity={i === partial ? .6 : 1} style={{ cursor: "pointer" }} {...tipProps(tip)} onClick={() => onClick?.(i)} />;
            })}
            <text x={x + bw / 2} y={H - 8} textAnchor="middle">{lb}</text>
          </g>;
        })}
      </svg>
  );
}

export type Item = { k: string; label: string; v: number; sub?: string; color?: string; tip?: string };
export function HBars({ items, onPick, sel, fmt = fN, color = "var(--s1)" }: {
  items: Item[]; onPick?: (k: string) => void; sel?: string; fmt?: (v: number) => string; color?: string;
}) {
  if (!items.length) return <div className="empty">Sem dados no recorte atual.</div>;
  const mx = Math.max(...items.map(i => i.v), 1);
  return <>{items.map(i => (
    <button key={i.k + i.label} className={`hb ${sel === i.k ? "sel" : ""}`} onClick={() => onPick?.(i.k)} style={{ cursor: onPick ? "pointer" : "default" }}
      {...tipProps(<><b>{i.label}</b>{fmt(i.v)}{i.tip && <><br />{i.tip}</>}</>)}>
      <span className="n">{i.label}{i.sub && <small>{i.sub}</small>}</span>
      <span className="tr"><i style={{ width: `${Math.max(1, i.v / mx * 100)}%`, ["--c" as any]: i.color || color }} /></span>
      <span className="x">{fmt(i.v)}</span>
    </button>))}</>;
}

export const Legend = ({ items }: { items: { n: string; c: string; line?: boolean }[] }) => (
  <div className="legend">{items.map(i => <span key={i.n}><i className={i.line ? "ln" : ""} style={{ background: i.c }} />{i.n}</span>)}</div>
);

export const Card = ({ title, cap, extra, children, className = "" }: { title: ReactNode; cap?: ReactNode; extra?: ReactNode; children: ReactNode; className?: string }) => (
  <section className={`card ${className}`}><div className="hd"><div><h3>{title}</h3>{cap && <div className="cap">{cap}</div>}</div>{extra}</div>{children}</section>
);

export const Kpi = ({ label, val, unit, d, color }: { label: string; val: string; unit?: string; d?: ReactNode; color: string }) => (
  <div className="card kpi" style={{ ["--k" as any]: color }}>
    <div className="l">{label}</div>
    <div className={`v ${val.length > 14 ? "long" : ""}`}>{val}{unit && <small>{unit}</small>}</div>
    <div className="d">{d}</div>
  </div>
);

/** Variação vs. período anterior; critérios: relevante ≥10%, acentuada ≥20%. upBad: aumento é ruim (tempos). */
export function Delta({ cur, prev, upBad }: { cur: number | null; prev: number | null | undefined; upBad?: boolean }) {
  const p = pct(cur, prev);
  if (p == null || !isFinite(p)) return <span>sem base comparável</span>;
  const a = Math.abs(p), cls = upBad == null ? "up" : (p > 0) === upBad ? "bad" : "good";
  return <>
    <span className={`dl ${cls}`}>{p > 0 ? "▲" : p < 0 ? "▼" : "■"} {f1(a)}%</span>
    {a >= 20 ? <span className="badge a" title="Variação acentuada (≥20%)">acentuada</span> : a >= 10 ? <span className="badge r" title="Variação relevante (≥10%)">relevante</span> : null}
    <span>vs. período anterior</span>
  </>;
}

export const Seg = <T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) => (
  <div className="seg">{options.map(([k, l]) => <button key={k} aria-pressed={value === k} onClick={() => onChange(k)}>{l}</button>)}</div>
);
