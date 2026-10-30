// Drill-down até o dia: abre por ?dia=AAAA-MM-DD (link compartilhável) e permite
// filtrar o painel inteiro clicando num setor, serviço ou atendente do dia.
import { useEffect } from "react";
import { linhas } from "./api";
import { HBars, Kpi } from "./charts";
import { fD, fN, fT, tc, WD, diaSemana } from "./fmt";
import { q, useBI, usePainel } from "./painel";

export function DiaDrawer() {
  const { st, set, toggle, setorColor } = usePainel();
  const d = st.dia;
  const f = { de: d, ate: d };
  const r = useBI({
    cal: q("calendario", ["dias"], ["tipo_dia"], { filtros: f }),
    ouv: q("ouvidoria", ["mensagens"], ["setor"], { filtros: f, ordem: ["-mensagens"] }),
    svc: q("servicos", ["servicos"], ["servico"], { filtros: f, ordem: ["-servicos"] }),
    hrs: q("atendimentos", ["atendimentos"], ["hora"], { filtros: f }),
    eq: q("tempos", ["atendimentos", "tme", "tma"], ["atendente"], { filtros: f, ordem: ["-atendimentos"] }),
  }, !!d);
  const fecha = () => set({ dia: null });
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && fecha();
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  });
  if (!d) return null;
  const R = r.data;
  const ouv = linhas(R?.ouv), svc = linhas(R?.svc), hrs = linhas(R?.hrs), eq = linhas(R?.eq);
  const totOuv = ouv.reduce((t, x) => t + x.mensagens, 0), totAtd = hrs.reduce((t, x) => t + x.atendimentos, 0);
  const totSvc = svc.reduce((t, x) => t + x.servicos, 0);
  const vazio = <div className="empty">Sem registros.</div>;
  return <>
    <div id="scrim" className="open" onClick={fecha} />
    <aside id="drawer" className="open" aria-label="Detalhe do dia">
      <button className="chip" onClick={fecha} style={{ float: "right" }}>Fechar ✕</button>
      <h2>{WD[diaSemana(d)]}, {fD(d)}</h2>
      <div className="cap" style={{ color: "var(--ink-3)", marginBottom: 14 }}>{linhas(R?.cal)[0]?.tipo_dia ?? ""}</div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(3,1fr)", marginBottom: 14 }}>
        <Kpi label="Ouvidoria" val={fN(totOuv)} color="var(--s2)" />
        <Kpi label="Atendimentos" val={fN(totAtd)} color="var(--s1)" />
        <Kpi label="Serviços" val={fN(totSvc)} color="var(--s3)" />
      </div>
      <h3 style={{ fontSize: 14 }}>Ouvidoria por setor</h3>
      {ouv.length ? <HBars items={ouv.map(o => ({ k: o.setor, label: tc(o.setor), v: o.mensagens, color: setorColor(o.setor) }))} onPick={k => toggle("setor", k)} sel={st.setor} /> : vazio}
      <h3 style={{ fontSize: 14, marginTop: 16 }}>Serviços executados</h3>
      {svc.length ? <HBars items={svc.map(o => ({ k: o.servico, label: o.servico, v: o.servicos }))} onPick={k => toggle("servico", k)} sel={st.servico} color="var(--s3)" /> : vazio}
      <h3 style={{ fontSize: 14, marginTop: 16 }}>Atendimentos por hora</h3>
      {hrs.length ? <HBars items={hrs.map(o => ({ k: String(o.hora), label: o.hora == null ? "sem hora" : `${String(o.hora).padStart(2, "0")}h`, v: o.atendimentos }))} /> : vazio}
      <h3 style={{ fontSize: 14, marginTop: 16 }}>Equipe no dia</h3>
      {eq.length ? <table className="t"><thead><tr><th>Atendente</th><th>Atend.</th><th>TME</th><th>TMA</th></tr></thead>
        <tbody>{eq.map(o => <tr key={o.atendente} onClick={() => toggle("atendente", o.atendente)}><td>{o.atendente}</td><td>{o.atendimentos}</td><td>{fT(o.tme)}</td><td>{fT(o.tma)}</td></tr>)}</tbody></table> : vazio}
    </aside>
  </>;
}
