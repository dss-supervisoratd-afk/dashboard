// As cinco abas do painel. Cada aba pede um lote de consultas à camada semântica e
// monta os gráficos; filtros cruzados (setor/serviço/atendente) e recorte vêm da URL.
import { useState, type ReactNode } from "react";
import { linhas, type Consulta, type Filtros, type Resultado, type Row } from "./api";
import { Card, Delta, HBars, Kpi, Legend, Seg, Stack, XY, type Serie } from "./charts";
import { f1, fD, fDs, fM, fN, fT, pct, sum, tc, WD } from "./fmt";
import { consultasDias, diasComDados, q, useBI, usePainel } from "./painel";
import { tipProps } from "./tip";

const pref = (p: string, o: Record<string, Consulta>) => Object.fromEntries(Object.entries(o).map(([k, v]) => [p + k, v]));
const porChave = (rs: Row[], k: string, v: string) => Object.fromEntries(rs.map(r => [r[k], r[v]]));
const v0 = (R: Record<string, Resultado> | undefined, k: string, m: string) => linhas(R?.[k])[0]?.[m] ?? null;
const tt = (v: number | null) => v == null ? "–" : fT(v);

function Carregando({ r, children }: { r: { isLoading: boolean; error: Error | null }; children: () => ReactNode }) {
  if (r.error) return <div className="erro">Falha ao consultar: {r.error.message}</div>;
  if (r.isLoading) return <div className="empty">Carregando…</div>;
  return <>{children()}</>;
}

/* ---------- blocos compartilhados ---------- */
function useMesSel() {
  const { meta, st, full } = usePainel();
  if (full) return null;
  const s = new Set(meta.meses.map((m, i) => `${m}-31` >= st.de && `${m}-01` <= st.ate ? i : -1).filter(i => i >= 0));
  return s.size ? s : null;
}

function Mensal({ valores, dias, color, title, unit }: { valores: Record<string, number>; dias: Record<string, number>; color: string; title: string; unit: string }) {
  const { meta, st, set, mes } = usePainel();
  const sel = useMesSel(), avg = st.mmode === "media";
  const ys = meta.meses.map(m => avg ? (dias[m] ? (valores[m] || 0) / dias[m] : null) : (valores[m] || 0));
  const ip = meta.parcial ? meta.meses.indexOf(meta.parcial) : -1;
  return <Card title={title} cap={avg ? `Média por dia com atendimento · ${unit}` : `Total mensal · ${unit} · mês parcial tracejado`}
    extra={<Seg value={st.mmode} options={[["total", "Total"], ["media", "Média/dia"]]} onChange={v => set({ mmode: v === "total" ? null : v })} />}>
    <XY labels={meta.meses.map(fM)} tips={meta.meses.map(m => fM(m) + (m === meta.parcial ? ` (parcial até ${fDs(meta.ate)})` : ""))}
      bars={[{ name: avg ? "Média/dia" : "Total", color, ys, tf: avg ? f1 : fN }]} partial={new Set(ip >= 0 ? [ip] : [])} sel={sel}
      yfmt={avg ? f1 : fN} h={220} lw={44} extra={i => <div style={{ opacity: .75, marginTop: 3 }}>{dias[meta.meses[i]] || 0} dias com dados</div>}
      onClick={i => mes(meta.meses[i])} aria={title} />
  </Card>;
}

function Diario({ cal, valores, incluir, kind }: { cal: Row[]; valores: Record<string, number>; incluir: (d: Row) => boolean; kind: "ouv" | "atd" }) {
  const { set } = usePainel();
  const days = cal.filter(incluir);
  const ys = days.map(d => valores[d.data] || 0);
  const ma = ys.map((_, i) => i < 6 ? null : sum(ys.slice(i - 6, i + 1), x => x) / 7);
  return <XY labels={days.map(d => fDs(d.data))} tips={days.map(d => `${WD[d.dia_semana]}, ${fD(d.data)} · ${d.tipo_dia}`)}
    bars={[{ name: kind === "ouv" ? "Mensagens" : "Atendimentos", color: kind === "ouv" ? "var(--s2)" : "var(--s1)", ys }]}
    lines={[{ name: "Média móvel 7 dias", color: "var(--ink-2)", ys: ma, tf: f1 }]} h={230} onClick={i => set({ dia: days[i].data })} aria="Série diária" />;
}

const incluiOuv = (ouv: Record<string, number>) => (d: Row) => !!ouv[d.data] || d.dia_semana % 6 !== 0;
const incluiAtd = (atd: Record<string, number>, svc: Set<string>) => (d: Row) => !!atd[d.data] || svc.has(d.data);

const calQ = (f: Filtros) => q("calendario", ["dias"], ["data", "dia_semana", "tipo_dia"], { filtros: f });
const mesesComDados = (datas: Set<string>, tipoOk = true) => {
  const out: Record<string, number> = {};
  if (tipoOk) datas.forEach(d => { out[d.slice(0, 7)] = (out[d.slice(0, 7)] || 0) + 1; });
  return out;
};

/* ---------- Visão geral ---------- */
export function Geral() {
  const { filtros: f, prev, st, meta, set } = usePainel();
  const base = (ff: Filtros) => ({
    ouv: q("ouvidoria", ["mensagens"], [], { filtros: ff }), atd: q("atendimentos", ["atendimentos"], [], { filtros: ff }),
    svc: q("servicos", ["servicos"], [], { filtros: ff }), tmp: q("tempos", ["tme", "tma"], [], { filtros: ff }),
  });
  const r = useBI({
    ...pref("c_", base(f)), ...(prev ? pref("p_", base(prev)) : {}), ...consultasDias(f),
    m_ouv: q("ouvidoria", ["mensagens"], ["mes"], { filtros: f, ignorar: ["periodo"] }),
    m_atd: q("atendimentos", ["atendimentos"], ["mes"], { filtros: f, ignorar: ["periodo"] }),
    cal: calQ(f),
    d_ouv: q("ouvidoria", ["mensagens"], ["data"], { filtros: f }),
    d_atd: q("atendimentos", ["atendimentos"], ["data"], { filtros: f }),
    d_tmp: q("tempos", ["atendimentos", "tme"], ["data"], { filtros: f }),
  });
  return <Carregando r={r}>{() => {
    const R = r.data!;
    const M = { ouv: v0(R, "c_ouv", "mensagens") ?? 0, atd: v0(R, "c_atd", "atendimentos") ?? 0, svc: v0(R, "c_svc", "servicos") ?? 0,
      tme: v0(R, "c_tmp", "tme"), tma: v0(R, "c_tmp", "tma") };
    const P = prev ? { ouv: v0(R, "p_ouv", "mensagens") ?? 0, atd: v0(R, "p_atd", "atendimentos") ?? 0, svc: v0(R, "p_svc", "servicos") ?? 0,
      tme: v0(R, "p_tmp", "tme"), tma: v0(R, "p_tmp", "tma") } : null;
    const todas = diasComDados(R), noRecorte = [...todas].filter(d => d >= st.de && d <= st.ate);
    const diasMes = mesesComDados(todas);
    const dOuv = porChave(linhas(R.d_ouv), "data", "mensagens"), dAtd = porChave(linhas(R.d_atd), "data", "atendimentos");
    const diasAtd = Object.keys(dAtd).length, nd = Math.max(1, noRecorte.length);
    const cal = linhas(R.cal);
    const svcDias = new Set(linhas(R.dias_servicos).map(x => x.data).filter((d: string) => d >= st.de && d <= st.ate));
    const d = (k: keyof typeof M, bad?: boolean) => P ? <Delta cur={M[k]} prev={P[k]} upBad={bad} /> : <span>sem período anterior</span>;

    const dest: [string, ReactNode][] = [];
    const pico = (o: Record<string, number>) => Object.entries(o).sort((a, b) => b[1] - a[1])[0];
    const abre = (dia: string) => <a href="#" onClick={e => { e.preventDefault(); set({ dia }); }}>{fD(dia)}</a>;
    const po = pico(dOuv), pa = pico(dAtd);
    if (po) dest.push(["", <>Pico de ouvidoria: <b>{fN(po[1])}</b> mensagens em {abre(po[0])} ({WD[new Date(po[0] + "T12:00").getDay()]}); média do recorte: {f1(M.ouv / nd)}/dia.</>]);
    if (pa) dest.push(["", <>Pico presencial: <b>{fN(pa[1])}</b> atendimentos concluídos em {abre(pa[0])}.</>]);
    const w = linhas(R.d_tmp).filter(x => x.atendimentos >= 20 && x.tme != null).sort((a, b) => b.tme - a.tme)[0];
    if (w) dest.push(["", <>Maior espera média (TME): <b>{fT(w.tme)}</b> em {abre(w.data)} (dias com ≥20 atendimentos).</>]);
    if (P) for (const [k, l, bad] of [["ouv", "Ouvidoria", false], ["atd", "Atendimentos concluídos", false], ["tme", "TME", true], ["tma", "TMA", true]] as const) {
      const p = pct(M[k], P[k]); if (p == null || Math.abs(p) < 10) continue;
      const a = Math.abs(p) >= 20;
      dest.push([a ? "a" : "r", <>{l}: variação {a ? "acentuada" : "relevante"} de <b>{p > 0 ? "+" : "−"}{f1(Math.abs(p))}%</b> sobre o período anterior de mesma duração.{bad && p > 0 ? " Piora de tempo — verificar se acompanha aumento de demanda." : ""}</>]);
    }
    if (meta.parcial && st.ate === meta.ate && st.de.slice(0, 7) <= meta.parcial)
      dest.push(["", <>O mês de <b>{fM(meta.parcial)}</b> é parcial (até {fD(meta.ate)}); não o compare a meses fechados sem usar “Média/dia”.</>]);

    return <>
      <div className="grid kpis">
        <Kpi label="Ouvidoria · mensagens" val={fN(M.ouv)} d={d("ouv")} color="var(--s2)" />
        <Kpi label="Atendimentos concluídos" val={fN(M.atd)} d={d("atd")} color="var(--s1)" />
        <Kpi label="Serviços executados" val={fN(M.svc)} d={d("svc")} color="var(--s3)" />
        <Kpi label="TME · espera média" val={tt(M.tme)} unit="min" d={d("tme", true)} color="var(--s4)" />
        <Kpi label="TMA · atendimento médio" val={tt(M.tma)} unit="min" d={d("tma", true)} color="var(--s7)" />
        <Kpi label="Dias com dados" val={fN(noRecorte.length)} d={<span>{f1(M.ouv / nd)} msgs/dia · {f1(M.atd / Math.max(1, diasAtd))} atend./dia</span>} color="var(--ink-3)" />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Mensal valores={porChave(linhas(R.m_ouv), "mes", "mensagens")} dias={diasMes} color="var(--s2)" title="Ouvidoria por mês" unit="mensagens" />
        <Mensal valores={porChave(linhas(R.m_atd), "mes", "atendimentos")} dias={diasMes} color="var(--s1)" title="Atendimentos concluídos por mês" unit="atendimentos" />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Ouvidoria por dia" cap={`${fD(st.de)} a ${fD(st.ate)} · mensagens · clique numa barra para abrir o dia`}>
          <Diario cal={cal} valores={dOuv} incluir={incluiOuv(dOuv)} kind="ouv" /></Card>
        <Card title="Atendimento presencial por dia" cap={`${fD(st.de)} a ${fD(st.ate)} · atendimentos concluídos · clique para abrir o dia`}>
          <Diario cal={cal} valores={dAtd} incluir={incluiAtd(dAtd, svcDias)} kind="atd" /></Card>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Destaques automáticos" cap="Critérios: variação relevante ≥10%, acentuada ≥20%">
          {dest.length ? <ul className="ins">{dest.map(([c, t], i) => <li key={i} className={c}>{t}</li>)}</ul> : <div className="empty">Nenhum destaque no recorte.</div>}
        </Card>
        <Card title="Como usar" cap="Drill-down e filtros cruzados">
          <ul className="ins">
            <li>Clique numa <b>barra mensal</b> para recortar o período naquele mês; nas barras diárias, para abrir o <b>detalhe do dia</b>.</li>
            <li>Nas abas, clique num <b>setor, serviço ou atendente</b> para filtrar o painel inteiro; remova pelo “×” na faixa de filtros.</li>
            <li>O endereço da página guarda o recorte: <b>copie o link</b> para compartilhar exatamente esta visão; “Voltar” desfaz o último clique.</li>
          </ul>
          <div className="note">Atendimentos concluídos = tickets do relatório “Atendimentos Concluídos”; Serviços executados = “Presenciais Executados” (um atendimento pode executar mais de um serviço).</div>
        </Card>
      </div>
    </>;
  }}</Carregando>;
}

/* ---------- Ouvidoria ---------- */
export function Ouvidoria() {
  const { filtros: f, st, toggle, setorColor, meta, mes } = usePainel();
  const r = useBI({
    set: q("ouvidoria", ["mensagens"], ["setor"], { filtros: f, ignorar: ["setor"], ordem: ["-mensagens"] }),
    sub: q("ouvidoria", ["mensagens"], ["setor", "subsetor"], { filtros: f, ordem: ["-mensagens"] }),
    stk: q("ouvidoria", ["mensagens"], ["mes", "setor"], { filtros: f, ignorar: ["periodo"] }),
    wd: q("ouvidoria", ["mensagens"], ["dia_semana"], { filtros: f }),
    d_all: q("ouvidoria", ["mensagens"], ["data"], { filtros: f, ignorar: ["setor"] }),
    d_ouv: q("ouvidoria", ["mensagens"], ["data"], { filtros: f }),
    cal: calQ(f),
  });
  return <Carregando r={r}>{() => {
    const R = r.data!;
    const setores = linhas(R.set), subs = linhas(R.sub), totAll = sum(setores, x => x.mensagens), tot = sum(subs, x => x.mensagens);
    const setItems = setores.map(s => ({ k: s.setor, label: tc(s.setor), v: s.mensagens, color: setorColor(s.setor), tip: `${f1(s.mensagens / totAll * 100)}% do total` }));
    const subItems = subs.slice(0, 30).map(s => ({ k: s.setor, label: tc(s.subsetor), sub: st.setor ? "" : tc(s.setor), v: s.mensagens, color: setorColor(s.setor),
      tip: `${f1(s.mensagens / Math.max(1, tot) * 100)}% do filtro` }));
    const dAll = porChave(linhas(R.d_all), "data", "mensagens"), cal = linhas(R.cal);
    const wdDias = Array(7).fill(0); cal.forEach(x => { if (dAll[x.data] || x.dia_semana % 6) wdDias[x.dia_semana]++; });
    const wdTot = Array(7).fill(0); linhas(R.wd).forEach(x => { wdTot[x.dia_semana] = x.mensagens; });
    const wdAvg = wdTot.map((v, i) => wdDias[i] ? v / wdDias[i] : null);
    const top = meta.setores.slice(0, 7);
    const series: Serie[] = [...top.map(s => ({ name: s, color: setorColor(s), ys: meta.meses.map(() => 0) as number[] })), { name: "Outros", color: "var(--other)", ys: meta.meses.map(() => 0) }];
    linhas(R.stk).forEach(x => { const i = meta.meses.indexOf(x.mes), j = top.indexOf(x.setor); if (i >= 0) (series[j < 0 ? 7 : j].ys as number[])[i] += x.mensagens; });
    const diasReg = Object.keys(dAll).length, dOuv = porChave(linhas(R.d_ouv), "data", "mensagens");
    return <>
      <div className="grid kpis">
        <Kpi label="Mensagens no recorte" val={fN(tot)} d={<span>{f1(tot / Math.max(1, diasReg))} por dia com registro</span>} color="var(--s2)" />
        <Kpi label="Setores ativos" val={fN(setores.length)} d={<span>{fN(subs.length)} subsetores{st.setor ? " no setor filtrado" : ""}</span>} color="var(--s1)" />
        <Kpi label="Maior setor" val={setItems[0] ? tc(setItems[0].k) : "–"} d={<span>{setItems[0] ? f1(setItems[0].v / totAll * 100) + "% do total" : ""}</span>} color="var(--s3)" />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Ouvidoria por setor" cap="Clique para filtrar o painel · mensagens"><div className="scroll"><HBars items={setItems} onPick={k => toggle("setor", k)} sel={st.setor} /></div></Card>
        <Card title={st.setor ? `Subsetores de ${tc(st.setor)}` : "Subsetores mais demandados"} cap="Drill-down: selecione um setor ao lado · top 30">
          <div className="scroll"><HBars items={subItems} onPick={k => toggle("setor", k)} sel={st.setor} /></div></Card>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Evolução mensal por setor" cap="Mensagens · 7 maiores setores · clique no mês para detalhar">
          <Legend items={[...top.map(s => ({ n: tc(s), c: setorColor(s) })), { n: "Outros", c: "var(--other)" }]} />
          <Stack labels={meta.meses.map(fM)} series={series} fmtSerie={tc} partial={meta.parcial ? meta.meses.indexOf(meta.parcial) : undefined} onClick={i => mes(meta.meses[i])} />
        </Card>
        <Card title="Média por dia da semana" cap="Mensagens por dia · sazonalidade semanal">
          <XY labels={WD} bars={[{ name: "Média de mensagens", color: "var(--s2)", ys: wdAvg, tf: f1 }]} yfmt={f1} h={250} lw={40} extra={i => <div style={{ opacity: .75 }}>{wdDias[i]} dias no recorte</div>} />
        </Card>
      </div>
      <div className="grid" style={{ marginTop: 16 }}>
        <Card title="Ouvidoria por dia" cap="Clique numa barra para abrir o dia"><Diario cal={cal} valores={dOuv} incluir={incluiOuv(dOuv)} kind="ouv" /></Card>
      </div>
    </>;
  }}</Carregando>;
}

/* ---------- Presencial ---------- */
const FAIXAS = ["até 5", "5–10", "10–20", "20–30", "30+"];
export function Presencial() {
  const { filtros: f, st, toggle, meta } = usePainel();
  const r = useBI({
    tot: q("atendimentos", ["atendimentos", "duracao_media"], [], { filtros: f }), tmp: q("tempos", ["tme", "tmd", "tma"], [], { filtros: f }),
    sv: q("atendimentos", ["atendimentos"], ["servico"], { filtros: f, ordem: ["-atendimentos"] }),
    se: q("servicos", ["servicos"], ["servico"], { filtros: f, ordem: ["-servicos"] }),
    heat: q("atendimentos", ["atendimentos"], ["dia_semana", "hora"], { filtros: f }),
    hdias: q("atendimentos", ["dias"], ["dia_semana"], { filtros: f, ignorar: ["servico", "atendente"] }),
    dur: q("atendimentos", ["atendimentos"], ["faixa_duracao"], { filtros: f }),
    tmo: q("tempos", ["tme", "tmd", "tma"], ["mes"], { filtros: f, ignorar: ["periodo"] }),
    hrs: q("atendimentos", ["atendimentos"], ["hora"], { filtros: f }),
    d_atd: q("atendimentos", ["atendimentos"], ["data"], { filtros: f }),
    cal: calQ(f), ...consultasDias(f),
  });
  return <Carregando r={r}>{() => {
    const R = r.data!;
    const tot = linhas(R.tot)[0] ?? {}, tm = linhas(R.tmp)[0] ?? {}, atd = tot.atendimentos ?? 0;
    const dias = [...diasComDados(R)].filter(d => d >= st.de && d <= st.ate).length;
    const svItems = linhas(R.sv).map(x => ({ k: x.servico, label: x.servico, v: x.atendimentos, tip: `${f1(x.atendimentos / Math.max(1, atd) * 100)}% dos atendimentos` }));
    const seItems = linhas(R.se).map(x => ({ k: x.servico, label: x.servico, v: x.servicos }));
    const heat = linhas(R.heat).filter(x => x.hora != null), hours = [...new Set(heat.map(x => x.hora as number))].sort((a, b) => a - b);
    const wdDias = porChave(linhas(R.hdias), "dia_semana", "dias"), cell: Record<string, number> = {};
    heat.forEach(x => { cell[`${x.dia_semana}_${x.hora}`] = x.atendimentos; });
    let mx = 0; Object.entries(cell).forEach(([k, v]) => { mx = Math.max(mx, v / (wdDias[+k.split("_")[0]] || 1)); });
    const durMap = porChave(linhas(R.dur), "faixa_duracao", "atendimentos");
    const tmo = Object.fromEntries(linhas(R.tmo).map(x => [x.mes, x]));
    const t = (k: string) => meta.meses.map(m => tmo[m]?.[k] != null ? tmo[m][k] / 60 : null);
    const hr = linhas(R.hrs).filter(x => x.hora != null);
    const dAtd = porChave(linhas(R.d_atd), "data", "atendimentos");
    const svcDias = new Set(linhas(R.dias_servicos).map(x => x.data as string));
    return <>
      <div className="grid kpis">
        <Kpi label="Atendimentos concluídos" val={fN(atd)} d={<span>{fN(dias)} dias</span>} color="var(--s1)" />
        <Kpi label="Duração média (SGA)" val={tt(tot.duracao_media)} unit="min" d={<span>por ticket concluído</span>} color="var(--s7)" />
        <Kpi label="TME · espera" val={tt(tm.tme)} unit="min" d={<span>média ponderada</span>} color="var(--s4)" />
        <Kpi label="TMD · deslocamento" val={tt(tm.tmd)} unit="min" d={<span>média ponderada</span>} color="var(--s3)" />
        <Kpi label="TMA · atendimento" val={tt(tm.tma)} unit="min" d={<span>média ponderada</span>} color="var(--s1)" />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Serviço triado" cap="Atendimentos concluídos · clique para filtrar (afeta também atendentes e tempos)">
          <div className="scroll"><HBars items={svItems} onPick={k => toggle("servico", k)} sel={st.servico} /></div></Card>
        <Card title="Serviços executados" cap="Relatório “Presenciais Executados” · clique para filtrar">
          <div className="scroll"><HBars items={seItems} onPick={k => toggle("servico", k)} sel={st.servico} color="var(--s3)" /></div></Card>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Intensidade por dia da semana e hora" cap="Média de atendimentos concluídos por dia · início da chamada">
          {hours.length ? <div style={{ overflowX: "auto" }}><div className="heat" style={{ gridTemplateColumns: `44px repeat(${hours.length},1fr)` }}>
            <div className="h" />{hours.map(h => <div key={h} className="h">{h}h</div>)}
            {[1, 2, 3, 4, 5, 6, 0].filter(w => wdDias[w]).map(w => [
              <div key={`l${w}`} className="h" style={{ justifyContent: "start" }}>{WD[w]}</div>,
              ...hours.map(h => {
                const c = cell[`${w}_${h}`] || 0, v = c / wdDias[w], p = mx ? v / mx * 100 : 0;
                return <div key={`${w}_${h}`} style={{ background: `color-mix(in srgb,var(--s1) ${Math.round(p * .92)}%,var(--surface-2))`, ...(p > 58 && { color: "#fff" }) }}
                  {...tipProps(<><b>{WD[w]} · {h}h</b>{f1(v)} atendimentos/dia<br />{fN(c)} no recorte</>)}>{v >= 1 ? f1(v) : v > 0 ? "<1" : ""}</div>;
              })])}
          </div></div> : <div className="empty">Sem dados no recorte atual.</div>}
        </Card>
        <Card title="Distribuição da duração" cap="Atendimentos por faixa de duração (minutos)">
          <XY labels={FAIXAS} bars={[{ name: "Atendimentos", color: "var(--s7)", ys: FAIXAS.map(k => durMap[k] || 0) }]} h={240} lw={40} />
        </Card>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Tempos médios por mês" cap="Minutos · média ponderada por atendimentos · mês parcial incluído">
          <Legend items={[{ n: "TME espera", c: "var(--s2)", line: true }, { n: "TMD deslocamento", c: "var(--s3)", line: true }, { n: "TMA atendimento", c: "var(--s1)", line: true }]} />
          <XY labels={meta.meses.map(fM)} lines={[{ name: "TME", color: "var(--s2)", ys: t("tme") }, { name: "TMD", color: "var(--s3)", ys: t("tmd") }, { name: "TMA", color: "var(--s1)", ys: t("tma") }]} yfmt={f1} h={240} lw={44} />
        </Card>
        <Card title="Atendimentos por hora" cap="Total no recorte · hora da chamada">
          <XY labels={hr.map(x => x.hora + "h")} bars={[{ name: "Atendimentos", color: "var(--s1)", ys: hr.map(x => x.atendimentos) }]} h={260} lw={36} />
        </Card>
      </div>
      <div className="grid" style={{ marginTop: 16 }}>
        <Card title="Atendimento presencial por dia" cap="Clique numa barra para abrir o dia"><Diario cal={linhas(R.cal)} valores={dAtd} incluir={incluiAtd(dAtd, svcDias)} kind="atd" /></Card>
      </div>
    </>;
  }}</Carregando>;
}

/* ---------- Equipe ---------- */
type Ord = [string, 1 | -1];
const ordena = (rows: Row[], [k, dir]: Ord) => [...rows].sort((a, b) => typeof a[k] === "string" ? dir * String(a[k]).localeCompare(String(b[k])) : dir * ((a[k] ?? -1) - (b[k] ?? -1)));
function Th({ k, l, ord, setOrd }: { k: string; l: string; ord: Ord; setOrd: (o: Ord) => void }) {
  return <th onClick={() => setOrd([k, ord[0] === k ? (-ord[1] as 1 | -1) : (["data", "atendente", "tipo_dia"].includes(k) ? 1 : -1)])}>{l}{ord[0] === k ? (ord[1] > 0 ? " ▲" : " ▼") : ""}</th>;
}

export function Equipe() {
  const { filtros: f, st, toggle, meta } = usePainel();
  const [ord, setOrd] = useState<Ord>(["atendimentos", -1]);
  const r = useBI({
    lst: q("tempos", ["atendimentos", "dias", "tme", "tmd", "tma"], ["atendente"], { filtros: f }),
    gm: q("tempos", ["tme", "tmd", "tma"], [], { filtros: f }),
    ...(st.atendente ? {
      sv: q("atendimentos", ["atendimentos"], ["servico"], { filtros: f, ordem: ["-atendimentos"], limite: 12 }),
      mm: q("tempos", ["atendimentos"], ["mes"], { filtros: f, ignorar: ["periodo"] }),
    } : {}),
  });
  return <Carregando r={r}>{() => {
    const R = r.data!;
    const list: Row[] = linhas(R.lst).map(o => ({ ...o, perDia: o.atendimentos / Math.max(1, o.dias) }));
    const gm = linhas(R.gm)[0] ?? {};
    const top = [...list].sort((a, b) => b.atendimentos - a.atendimentos).slice(0, 15)
      .map(o => ({ k: o.atendente, label: o.atendente, v: o.atendimentos, tip: `${f1(o.perDia)} atendimentos/dia · ${o.dias} dias` }));
    const mm = porChave(linhas(R.mm), "mes", "atendimentos"), ip = meta.parcial ? meta.meses.indexOf(meta.parcial) : -1;
    const th = (k: string, l: string) => <Th k={k} l={l} ord={ord} setOrd={setOrd} />;
    return <>
      <div className="grid kpis">
        <Kpi label="Atendentes no recorte" val={fN(list.length)} d={<span>{fN(sum(list, o => o.atendimentos))} atendimentos</span>} color="var(--s1)" />
        <Kpi label="TME médio" val={tt(gm.tme)} unit="min" d={<span>equipe</span>} color="var(--s2)" />
        <Kpi label="TMD médio" val={tt(gm.tmd)} unit="min" d={<span>equipe</span>} color="var(--s3)" />
        <Kpi label="TMA médio" val={tt(gm.tma)} unit="min" d={<span>equipe</span>} color="var(--s7)" />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Volume por atendente" cap="Top 15 · clique para filtrar o painel"><HBars items={top} onPick={k => toggle("atendente", k)} sel={st.atendente} /></Card>
        <Card title="Quadro da equipe" cap="Clique no cabeçalho para ordenar e na linha para filtrar · tempos em min:s">
          <div className="scroll"><table className="t"><thead><tr>{th("atendente", "Atendente")}{th("atendimentos", "Atend.")}{th("dias", "Dias")}{th("perDia", "/dia")}{th("tme", "TME")}{th("tmd", "TMD")}{th("tma", "TMA")}</tr></thead>
            <tbody>{ordena(list, ord).map(o => <tr key={o.atendente} className={st.atendente === o.atendente ? "sel" : ""} onClick={() => toggle("atendente", o.atendente)}>
              <td>{o.atendente}</td><td>{fN(o.atendimentos)}</td><td>{o.dias}</td><td>{f1(o.perDia)}</td><td>{fT(o.tme)}</td><td>{fT(o.tmd)}</td><td>{fT(o.tma)}</td></tr>)}</tbody></table></div>
          <div className="note">Tempos de guichê e sala sem pessoa associada aparecem com o próprio rótulo do relatório.</div>
        </Card>
      </div>
      {st.atendente && <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title={`Serviços de ${st.atendente}`} cap="Atendimentos concluídos no recorte · clique para filtrar por serviço">
          <HBars items={linhas(R.sv).map(x => ({ k: x.servico, label: x.servico, v: x.atendimentos }))} onPick={k => toggle("servico", k)} sel={st.servico} /></Card>
        <Card title={`Volume mensal de ${st.atendente}`} cap="Atendimentos (relatório TMA)">
          <XY labels={meta.meses.map(fM)} bars={[{ name: "Atendimentos", color: "var(--s1)", ys: meta.meses.map(m => mm[m] || 0) }]} partial={new Set(ip >= 0 ? [ip] : [])} h={230} lw={44} /></Card>
      </div>}
    </>;
  }}</Carregando>;
}

/* ---------- Dados diários ---------- */
export function Dados() {
  const { filtros: f, set } = usePainel();
  const [ord, setOrd] = useState<Ord>(["data", 1]);
  const r = useBI({
    cal: calQ(f), ouv: q("ouvidoria", ["mensagens"], ["data"], { filtros: f }), atd: q("atendimentos", ["atendimentos"], ["data"], { filtros: f }),
    svc: q("servicos", ["servicos"], ["data"], { filtros: f }), tmp: q("tempos", ["tme", "tmd", "tma"], ["data"], { filtros: f }),
  });
  return <Carregando r={r}>{() => {
    const R = r.data!;
    const ouv = porChave(linhas(R.ouv), "data", "mensagens"), atd = porChave(linhas(R.atd), "data", "atendimentos"), svc = porChave(linhas(R.svc), "data", "servicos");
    const tmp = Object.fromEntries(linhas(R.tmp).map(x => [x.data, x]));
    const rows = linhas(R.cal).filter(d => ouv[d.data] || atd[d.data] || svc[d.data] || tmp[d.data]).map(d => ({
      data: d.data, wd: WD[d.dia_semana], tipo_dia: d.tipo_dia, ouv: ouv[d.data] || 0, atd: atd[d.data] || 0, svc: svc[d.data] || 0,
      tme: tmp[d.data]?.tme ?? null, tmd: tmp[d.data]?.tmd ?? null, tma: tmp[d.data]?.tma ?? null,
    }));
    const csv = () => {
      const h = ["data", "dia", "tipo", "ouvidoria", "atendimentos_concluidos", "servicos_executados", "tme_s", "tmd_s", "tma_s"];
      const r2 = (v: number | null) => v == null ? "" : Math.round(v);
      const txt = [h.join(";"), ...ordena(rows, ord).map(x => [x.data, x.wd, x.tipo_dia, x.ouv, x.atd, x.svc, r2(x.tme), r2(x.tmd), r2(x.tma)].join(";"))].join("\n");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob(["﻿" + txt], { type: "text/csv;charset=utf-8" }));
      a.download = `atendimento_${f.de}_${f.ate}.csv`; a.click();
    };
    const th = (k: string, l: string) => <Th k={k} l={l} ord={ord} setOrd={setOrd} />;
    return <Card title="Dados diários" cap={`${rows.length} dias · clique na linha para o detalhe do dia`} extra={<button className="chip" onClick={csv}>⬇ Exportar CSV</button>}>
      <div className="scroll" style={{ maxHeight: "70vh" }}><table className="t"><thead><tr>{th("data", "Data")}<th>Dia</th>{th("tipo_dia", "Tipo")}{th("ouv", "Ouvidoria")}{th("atd", "Atend.")}{th("svc", "Serviços")}{th("tme", "TME")}{th("tmd", "TMD")}{th("tma", "TMA")}</tr></thead>
        <tbody>{ordena(rows, ord).map(x => <tr key={x.data} onClick={() => set({ dia: x.data })}><td>{fD(x.data)}</td><td style={{ textAlign: "right" }}>{x.wd}</td><td>{x.tipo_dia}</td>
          <td>{fN(x.ouv)}</td><td>{fN(x.atd)}</td><td>{fN(x.svc)}</td><td>{fT(x.tme)}</td><td>{fT(x.tmd)}</td><td>{fT(x.tma)}</td></tr>)}</tbody></table></div>
    </Card>;
  }}</Carregando>;
}

