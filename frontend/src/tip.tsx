import { useSyncExternalStore, type ReactNode, type MouseEvent } from "react";

// tooltip único e global, posicionado junto ao cursor (como no painel original)
type St = { node: ReactNode; x: number; y: number } | null;
let st: St = null;
const subs = new Set<() => void>();
const emit = () => subs.forEach(f => f());

export function showTip(node: ReactNode, e: MouseEvent | globalThis.MouseEvent) {
  st = { node, x: e.clientX, y: e.clientY };
  emit();
}
export function hideTip() {
  if (st) { st = null; emit(); }
}
export const tipProps = (node: ReactNode) => ({
  onMouseMove: (e: MouseEvent) => showTip(node, e),
  onMouseLeave: hideTip,
});

export function Tooltip() {
  const s = useSyncExternalStore(f => { subs.add(f); return () => subs.delete(f); }, () => st);
  if (!s) return null;
  const w = 300, x = s.x + 14 + w > innerWidth - 8 ? s.x - w - 14 : s.x + 14;
  const y = s.y + 14 + 120 > innerHeight - 8 ? s.y - 120 : s.y + 14;
  return <div id="tip" style={{ display: "block", left: Math.max(8, x), top: Math.max(8, y) }}>{s.node}</div>;
}

export const TipRow = ({ cor, nome, valor }: { cor: string; nome: string; valor: string }) => (
  <div className="r"><span><i style={{ background: cor }} />{nome}</span><b style={{ display: "inline" }}>{valor}</b></div>
);
