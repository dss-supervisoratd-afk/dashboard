import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import type { MetaCheia } from "./api";
import { useAuth } from "./auth";
import { DiaDrawer } from "./dia";
import { fD, fDH, fM, tc } from "./fmt";
import { PainelCtx, useMeta, usePainel, usePainelEstado } from "./painel";
import { hideTip } from "./tip";

const ABAS_PAINEL: [string, string][] = [["/", "Visão geral"], ["/ouvidoria", "Ouvidoria (remoto)"], ["/presencial", "Presencial"],
  ["/equipe", "Equipe & tempos"], ["/dados", "Dados diários"]];

function alternaTema() {
  const el = document.documentElement;
  const cur = el.dataset.theme || (matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light");
  const nx = cur === "dark" ? "light" : "dark";
  el.dataset.theme = nx;
  try { localStorage.setItem("amn-theme", JSON.stringify(nx)); } catch { /* armazenamento bloqueado */ }
}

function MenuUsuario() {
  const { user, sair, pode } = useAuth();
  const [aberto, setAberto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const f = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setAberto(false);
    document.addEventListener("click", f);
    return () => document.removeEventListener("click", f);
  }, []);
  if (!user) return null;
  return (
    <div className="user" ref={ref}>
      <button className="ibtn" onClick={() => setAberto(!aberto)} aria-expanded={aberto}>{user.nome.split(" ")[0]} ▾</button>
      {aberto && <div className="menu" onClick={() => setAberto(false)}>
        <div className="who"><b>{user.nome}</b><small>{user.email}</small><small>Perfil: {user.papel}</small></div>
        <Link to="/conta">Minha conta</Link>
        {pode("usuarios:gerir") && <Link to="/usuarios">Usuários e papéis</Link>}
        {pode("auditoria:ver") && <Link to="/auditoria">Auditoria</Link>}
        <button onClick={sair}>Sair</button>
      </div>}
    </div>
  );
}

export function Shell() {
  const { pode } = useAuth();
  const { search, pathname } = useLocation();
  const meta = useMeta().data;
  useEffect(hideTip, [pathname, search]);
  const corte = meta && !meta.vazio ? `Dados de ${fD(meta.de)} a ${fD(meta.ate)}${meta.parcial ? " · " + fM(meta.parcial) + " parcial" : ""}` : "";
  return <>
    <header className="top">
      <div className="row">
        <div className="logo" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12" /><path d="M5 12a7 7 0 0 0 14 0" /><circle cx="12" cy="5" r="2" /><path d="M3 12h3M18 12h3" /></svg></div>
        <div><h1>Gestão do Atendimento ao Associado</h1><div className="sub">Associação Abrigo do Marinheiro · Gerência de Atendimento</div></div>
        <div className="sp" />
        <div className="sub">{corte}</div>
        <button className="ibtn" onClick={alternaTema} title="Alternar tema claro/escuro">◐ Tema</button>
        <button className="ibtn" onClick={() => print()}>Imprimir</button>
        <MenuUsuario />
      </div>
      <nav className="tabs" role="tablist">
        {/* abas do painel preservam o recorte (?de=&ate=…) ao navegar */}
        {ABAS_PAINEL.map(([to, l]) => <NavLink key={to} to={{ pathname: to, search: ABAS_PAINEL.some(a => a[0] === pathname) ? search : "" }} end
          className={({ isActive }) => isActive ? "on" : ""}>{l}</NavLink>)}
        {pode("dados:importar") && <><span className="sep" /><NavLink to="/importar" className={({ isActive }) => isActive ? "on" : ""}>Importar dados</NavLink></>}
      </nav>
    </header>
    <Outlet />
  </>;
}

/* ---------- painel: carrega o contexto (meta), filtros, rodapé e drawer ---------- */
export function PainelLayout() {
  const m = useMeta();
  const { pode } = useAuth();
  if (m.isLoading) return <main><div className="empty">Carregando…</div></main>;
  if (m.error) return <main><div className="erro">Falha ao carregar o painel: {String(m.error.message)}</div></main>;
  if (!m.data || m.data.vazio) return <main><div className="card vazio-hero">
    <h2>Nenhum dado carregado ainda</h2>
    <p>O painel é montado a partir das importações de Ouvidorias, Atendimentos Concluídos, Presenciais Executados e TMA.</p>
    {pode("dados:importar") ? <Link className="btn" to="/importar">Importar o primeiro arquivo</Link>
      : <p className="note">Peça a um gestor ou administrador para importar os relatórios.</p>}
  </div></main>;
  return <PainelComMeta meta={m.data} />;
}

function PainelComMeta({ meta }: { meta: MetaCheia }) {
  const p = usePainelEstado(meta);
  return <PainelCtx.Provider value={p}>
    <div className="filters"><div className="in"><Filtros /></div><Ativos /></div>
    <main><Outlet /></main>
    <Rodape />
    <DiaDrawer />
  </PainelCtx.Provider>;
}

function Filtros() {
  const { st, set, full, meta, mes } = usePainel();
  return <>
    <div className="fg"><label>Período</label><div className="chips">
      <button className="chip" aria-pressed={full} onClick={() => set({ de: null, ate: null })}>Tudo</button>
      <button className="chip" onClick={() => { const d = new Date(meta.ate + "T12:00:00"); d.setDate(d.getDate() - 29); const de = d.toISOString().slice(0, 10); set({ de: de < meta.de ? meta.de : de, ate: null }); }}>Últimos 30 dias</button>
      {meta.meses.map(m => <button key={m} className={`chip ${m === meta.parcial ? "partial" : ""}`} aria-pressed={!full && st.de === m + "-01"}
        title={m === meta.parcial ? "Mês parcial até " + fD(meta.ate) : ""} onClick={() => mes(m)}>{fM(m)}</button>)}
    </div></div>
    <div className="fg"><label htmlFor="f1">De</label>
      <input type="date" id="f1" value={st.de} min={meta.de} max={meta.ate} onChange={e => e.target.value && set({ de: e.target.value, ...(e.target.value > st.ate && { ate: e.target.value }) })} />
      <label htmlFor="f2">até</label>
      <input type="date" id="f2" value={st.ate} min={meta.de} max={meta.ate} onChange={e => e.target.value && set({ ate: e.target.value, ...(e.target.value < st.de && { de: e.target.value }) })} />
    </div>
    <div className="fg"><label htmlFor="ft">Tipo de dia</label>
      <select id="ft" value={st.tipo} onChange={e => set({ tipo: e.target.value || null })}>
        <option value="">Todos</option>
        {meta.tipos.map(([t, n]) => <option key={t} value={t}>{t} ({n})</option>)}
      </select></div>
  </>;
}

function Ativos() {
  const { st, set } = usePainel();
  const tags = ([["setor", "Setor", st.setor && tc(st.setor)], ["servico", "Serviço", st.servico], ["atendente", "Atendente", st.atendente],
    ["tipo", "Tipo de dia", st.tipo]] as const).filter(t => t[2]);
  if (!tags.length) return null;
  return <div className="active">
    {tags.map(([k, l, v]) => <span key={k} className="tag">{l}: <b>{v}</b><button aria-label="Remover filtro" onClick={() => set({ [k]: null })}>×</button></span>)}
    <button className="chip" onClick={() => set({ setor: null, servico: null, atendente: null, tipo: null, de: null, ate: null })}>Limpar tudo</button>
  </div>;
}

function Rodape() {
  const { meta } = usePainel();
  return <footer>
    <div className="fontes">{Object.entries(meta.fontes).map(([k, f]) => <span key={k} title={f.ultima_importacao ? "Última importação: " + fDH(f.ultima_importacao) : ""}>
      <b>{f.rotulo}</b>: {f.de ? `${fD(f.de)} a ${fD(f.ate!)}` : "sem dados"}</span>)}</div>
    Fontes: relatórios diários de Ouvidorias, Atendimentos Concluídos, Presenciais Executados e TMA (SGA), importados em lotes rastreáveis.
    O mês corrente é parcial e não deve ser comparado a meses fechados sem normalização (use “Média/dia”). Dados internos: não publicar externamente.
  </footer>;
}
