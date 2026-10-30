// Estado do painel na URL (?de=&ate=&tipo=&setor=&servico=&atendente=&mmode=&dia=):
// cada recorte e cada drill-down vira um link compartilhável e o botão Voltar desfaz o último clique.
import { createContext, useContext, useMemo } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, type Consulta, type Filtros, type Meta, type MetaCheia, type Resultado } from "./api";
import { addDias, fimDoMes } from "./fmt";

export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: () => api.get<Meta>("/api/bi/meta"), staleTime: 60_000 });

export function useBI(consultas: Record<string, Consulta>, enabled = true) {
  return useQuery({
    queryKey: ["bi", consultas], enabled, placeholderData: keepPreviousData, staleTime: 60_000,
    queryFn: () => api.post<Record<string, Resultado>>("/api/bi/lote", { consultas }),
  });
}

export const CRUZADOS = ["setor", "subsetor", "servico", "atendente"];
const CHAVES = ["de", "ate", "tipo", "setor", "servico", "atendente", "mmode", "dia"] as const;
type Chave = typeof CHAVES[number];

export function usePainelEstado(meta: MetaCheia) {
  const [sp, setSp] = useSearchParams();
  return useMemo(() => {
    const g = (k: Chave) => sp.get(k) || "";
    const st = {
      de: g("de") || meta.de, ate: g("ate") || meta.ate, tipo: g("tipo"), setor: g("setor"), servico: g("servico"),
      atendente: g("atendente"), mmode: g("mmode") === "media" ? "media" as const : "total" as const, dia: g("dia"),
    };
    const set = (patch: Partial<Record<Chave, string | null>>) => setSp(prev => {
      const n = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(patch)) v ? n.set(k, v) : n.delete(k);
      if (n.get("de") === meta.de) n.delete("de");
      if (n.get("ate") === meta.ate) n.delete("ate");
      return n;
    });
    const toggle = (k: "setor" | "servico" | "atendente", v: string) => set({ [k]: st[k] === v ? null : v });
    const filtros: Filtros = { de: st.de, ate: st.ate, ...(st.tipo && { tipo: st.tipo }), ...(st.setor && { setor: st.setor }),
      ...(st.servico && { servico: st.servico }), ...(st.atendente && { atendente: st.atendente }) };
    // período anterior de mesma duração (para as variações dos KPIs)
    const n = Math.round((+new Date(st.ate) - +new Date(st.de)) / 864e5) + 1;
    const pAte = addDias(st.de, -1), pDe = addDias(st.de, -n);
    const prev: Filtros | null = pAte < meta.de ? null : { ...filtros, de: pDe, ate: pAte };
    const full = st.de === meta.de && st.ate === meta.ate;
    const setorColor = (s: string) => { const i = meta.setores.indexOf(s); return i > -1 && i < 7 ? `var(--s${i + 1})` : "var(--other)"; };
    const mes = (m: string) => { let ate = fimDoMes(m); if (ate > meta.ate) ate = meta.ate; set({ de: `${m}-01`, ate }); };
    return { st, set, toggle, filtros, prev, full, setorColor, mes, meta };
  }, [sp, setSp, meta]);
}

export type Painel = ReturnType<typeof usePainelEstado>;
export const PainelCtx = createContext<Painel>(null!);
export const usePainel = () => useContext(PainelCtx);

/* consultas recorrentes */
export const q = (conjunto: string, medidas: string[], dims: string[] = [], extra: Partial<Consulta> = {}): Consulta =>
  ({ conjunto, medidas, dims, ...extra });

/** Dias com algum dado (qualquer fonte), ignorando filtros cruzados — base de "média por dia". */
export const consultasDias = (f: Filtros): Record<string, Consulta> => Object.fromEntries(
  ["ouvidoria", "atendimentos", "servicos", "tempos"].map(c => [`dias_${c}`, q(c, ["dias"], ["data"], { filtros: f, ignorar: ["periodo", ...CRUZADOS] })]));

export function diasComDados(r: Record<string, Resultado> | undefined): Set<string> {
  const s = new Set<string>();
  if (r) for (const c of ["ouvidoria", "atendimentos", "servicos", "tempos"]) r[`dias_${c}`]?.linhas.forEach(l => s.add(l[0]));
  return s;
}
