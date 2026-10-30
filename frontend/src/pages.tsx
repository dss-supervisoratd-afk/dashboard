import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import { api, type Perfil } from "./api";
import { useAuth } from "./auth";
import { Card } from "./charts";
import { fD, fDH, fN } from "./fmt";

/* ---------- Login ---------- */
const ERROS_OAUTH: Record<string, string> = {
  oauth: "Não foi possível concluir o login com o Google. Tente novamente.",
  email_nao_verificado: "A conta Google não tem email verificado.",
  nao_autorizado: "Esta conta Google não está autorizada. Peça acesso a um administrador.",
  inativo: "Seu usuário está desativado.",
};

export function Login() {
  const { user, recarregar } = useAuth();
  const [sp] = useSearchParams();
  const loc = useLocation() as { state?: { de?: string } };
  const prov = useQuery({ queryKey: ["provedores"], queryFn: () => api.get<{ google: boolean }>("/api/auth/provedores") });
  const [email, setEmail] = useState(""), [senha, setSenha] = useState("");
  const m = useMutation({ mutationFn: () => api.post<Perfil>("/api/auth/login", { email, senha }), onSuccess: recarregar });
  if (user) return <Navigate to={loc.state?.de || "/"} replace />;
  const erro = m.error?.message || ERROS_OAUTH[sp.get("erro") || ""];
  return <div className="login">
    <div className="card">
      <h1>Gestão do Atendimento</h1>
      <div className="cap" style={{ marginBottom: 16 }}>Associação Abrigo do Marinheiro · acesso restrito</div>
      <form className="form" onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate(); }}>
        {erro && <div className="erro" role="alert">{erro}</div>}
        <label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Senha<input type="password" autoComplete="current-password" required value={senha} onChange={e => setSenha(e.target.value)} /></label>
        <button className="btn" disabled={m.isPending}>{m.isPending ? "Entrando…" : "Entrar"}</button>
        {prov.data?.google && <>
          <div className="ou">ou</div>
          <a className="gbtn" href="/api/auth/google/login">
            <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.9 6.1C12.5 13.6 17.8 9.5 24 9.5z" /><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 7l7.2 5.6c4.2-3.9 7.1-9.6 7.1-17.1z" /><path fill="#FBBC05" d="M10.6 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.1C1 16.6 0 20.2 0 24s1 7.4 2.7 10.7l7.9-6.1z" /><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.2-5.6c-2 1.4-4.7 2.3-8.7 2.3-6.2 0-11.5-4.1-13.4-9.9l-7.9 6.1C6.6 42.6 14.6 48 24 48z" /></svg>
            Entrar com Google</a>
        </>}
      </form>
    </div>
  </div>;
}

/* ---------- Importação ---------- */
type Analise = {
  envio: string; arquivo: string; duplicado: { lote: number; em: string; conjunto: string } | null;
  automatico: boolean; tipo_arquivo: "legado" | "sga" | "cadastro" | "planilha"; autoconfiavel: boolean; tipo_dia: string | null;
  conjunto: string; avisos: string[]; colunas: string[]; amostra: string[][];
  // automático
  resumo?: Record<string, number>; de?: string; ate?: string; linhas?: number;
  // planilha
  abas: { nome: string; linhas: number }[]; aba: number; linha_cabecalho: number; total_linhas: number;
  confianca: number; ranking: [string, number][]; mapeamento: Record<string, number>; confianca_campos: Record<string, number>;
  unidades: Record<string, string>; campos: { nome: string; tipo: string; obrigatorio: boolean; descricao: string }[];
  data_arquivo: string | null;
  validacao: { validas: number; com_erro: number; erros: { linha: number; campo: string; valor: string; erro: string }[]; de: string | null; ate: string | null; dias: number };
};
type Lote = { id: number; conjunto: string; arquivo: string; status: string; linhas_lidas: number; linhas_carregadas: number; de: string | null; ate: string | null; avisos: string[]; usuario: string | null; criado_em: string };
type Esquemas = Record<string, { rotulo: string }>;
type Item = { nome: string; estado: "fila" | "lendo" | "gravado" | "pulado" | "conferir" | "erro"; msg?: string; analise?: Analise };

const nivel = (c: number) => c >= .75 ? "alta" : c >= .45 ? "media" : "baixa";
const Conf = ({ c }: { c: number }) => <span className={`conf ${nivel(c)}`} title="Confiança do reconhecimento">{Math.round(c * 100)}%</span>;
const EXTRA: Record<string, string> = { legado: "Painel legado (todos os conjuntos)", guiches: "Cadastro de guichês" };
const ORIGEM: Record<string, string> = { sga: "PDF do Novo SGA", cadastro: "Guichês - Tabela Consolidada", legado: "Painel HTML antigo" };
const ACEITOS = [".csv", ".txt", ".xlsx", ".xlsm", ".xls", ".pdf", ".html", ".htm"];
const eCadastro = (n: string) => /guich/i.test(n) && /consolid/i.test(n);
const ORDEM_ESTADO = ["erro", "conferir", "lendo", "fila", "gravado", "pulado"];

const enviaArquivo = (f: File) => { const fd = new FormData(); fd.append("arquivo", f); return api.post<Analise>("/api/importacoes/analisar", fd); };
const confirmaEnvio = (a: Analise) => api.post<{ lote: Lote; descartadas: number }>(`/api/importacoes/${a.envio}/confirmar`,
  a.automatico ? {} : { aba: a.aba, conjunto: a.conjunto, mapeamento: a.mapeamento, unidades: a.unidades });

export function Importar() {
  const qc = useQueryClient();
  const { pode } = useAuth();
  const esq = useQuery({ queryKey: ["esquemas"], queryFn: () => api.get<Esquemas>("/api/importacoes/esquemas") });
  const lotes = useQuery({ queryKey: ["lotes"], queryFn: () => api.get<Lote[]>("/api/importacoes") });
  const [a, setA] = useState<Analise | null>(null);
  const [fila, setFila] = useState<Item[]>([]);
  const [rodando, setRodando] = useState(false);
  const [reimportar, setReimportar] = useState(false);
  const [arrasto, setArrasto] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const atualiza = () => { qc.invalidateQueries({ queryKey: ["lotes"] }); qc.invalidateQueries({ queryKey: ["meta"] }); qc.invalidateQueries({ queryKey: ["bi"] }); };
  const rot = (c: string) => EXTRA[c] ?? esq.data?.[c]?.rotulo ?? c;

  const envia = useMutation({ mutationFn: enviaArquivo, onSuccess: r => { setA(r); setOk(null); } });
  const previa = useMutation({
    mutationFn: (op: object) => api.post<Analise>(`/api/importacoes/${a!.envio}/previa`, op),
    onSuccess: r => setA(x => ({ ...x!, ...r })),
  });
  const confirma = useMutation({
    mutationFn: () => confirmaEnvio(a!),
    onSuccess: r => {
      setOk(`Lote #${r.lote.id} carregado: ${fN(r.lote.linhas_carregadas)} linhas${r.descartadas ? `, ${r.descartadas} descartadas` : ""}.`);
      setFila(f => f.map(i => i.analise?.envio === a!.envio ? { ...i, estado: "gravado", msg: `${fN(r.lote.linhas_carregadas)} linhas` } : i));
      setA(null); atualiza();
    },
  });
  const reverte = useMutation({ mutationFn: (id: number) => api.del(`/api/importacoes/${id}`), onSuccess: atualiza });

  // vários arquivos: grava sozinho o que o sistema reconhece com segurança; o resto fica para conferência
  async function processa(files: File[]) {
    const lista = files.filter(f => ACEITOS.some(e => f.name.toLowerCase().endsWith(e)))
      .sort((x, y) => Number(eCadastro(y.name)) - Number(eCadastro(x.name)) || x.name.localeCompare(y.name));
    setA(null); setOk(null); setRodando(true);
    setFila(lista.map(f => ({ nome: f.name, estado: "fila" })));
    const marca = (i: number, p: Partial<Item>) => setFila(f => f.map((x, j) => j === i ? { ...x, ...p } : x));
    const um = async (i: number) => {
      marca(i, { estado: "lendo" });
      try {
        const r = await enviaArquivo(lista[i]);
        if (r.duplicado && !reimportar) marca(i, { estado: "pulado", msg: `já importado (lote #${r.duplicado.lote})` });
        else if (r.autoconfiavel) {
          const c = await confirmaEnvio(r);
          marca(i, { estado: "gravado", msg: `${rot(c.lote.conjunto)} · ${fN(c.lote.linhas_carregadas)} linhas` });
        } else marca(i, { estado: "conferir", msg: `${rot(r.conjunto)} · confiança ${Math.round((r.confianca ?? 0) * 100)}%`, analise: r });
      } catch (e) { marca(i, { estado: "erro", msg: (e as Error).message }); }
    };
    // o cadastro de guichês vai antes e sozinho, para os nomes dos demais já entrarem resolvidos
    let prox = 0;
    if (lista.length && eCadastro(lista[0].name)) await um(prox++);
    const trabalhador = async () => { while (prox < lista.length) await um(prox++); };
    await Promise.all([trabalhador(), trabalhador(), trabalhador()]);
    setRodando(false); atualiza();
  }

  const escolhe = (fs: FileList | null) => {
    if (!fs?.length) return;
    if (fs.length === 1) { setFila([]); envia.mutate(fs[0]); } else processa([...fs]);
  };
  const muda = (patch: Partial<Pick<Analise, "aba" | "conjunto" | "mapeamento" | "unidades">>) =>
    previa.mutate({ aba: a!.aba, conjunto: a!.conjunto, mapeamento: a!.mapeamento, unidades: a!.unidades, ...patch,
      ...(patch.conjunto || patch.aba != null ? { mapeamento: undefined } : {}) });
  const mapeadas = new Set(Object.values(a?.mapeamento ?? {}));
  const erro = envia.error || previa.error || confirma.error || reverte.error;
  const conta = (e: Item["estado"]) => fila.filter(i => i.estado === e).length;
  const dup = (x: Analise) => x.duplicado && <div className="aviso" style={{ marginBottom: 8 }}>Este mesmo arquivo já foi importado no lote #{x.duplicado.lote} ({fDH(x.duplicado.em)}). Reimportar substitui os mesmos dias, sem duplicar.</div>;
  const botoes = (n: number) => <div className="row" style={{ marginTop: 12 }}>
    <button className="btn" disabled={confirma.isPending || previa.isPending || (!a!.automatico && !n)} onClick={() => confirma.mutate()}>
      {confirma.isPending ? "Gravando…" : a!.automatico ? "Gravar" : `Gravar ${fN(n)} linhas`}</button>
    <button className="btn sec" onClick={() => setA(null)}>Cancelar</button></div>;

  return <main>
    <div className="grid g2">
      <Card title="Importar relatórios" cap="PDFs do Novo SGA, planilhas de Ouvidoria, cadastro de guichês, CSV/XLSX padronizados ou o painel HTML antigo">
        <label className={`drop ${arrasto ? "on" : ""}`} onDragOver={e => { e.preventDefault(); setArrasto(true); }} onDragLeave={() => setArrasto(false)}
          onDrop={e => { e.preventDefault(); setArrasto(false); escolhe(e.dataTransfer.files); }}>
          <input type="file" hidden multiple accept={ACEITOS.join(",")} onChange={e => { escolhe(e.target.files); e.target.value = ""; }} />
          {envia.isPending ? "Analisando…" : <><b>Arraste arquivos aqui</b> ou clique para escolher<br />
            <small>Um arquivo: conferência detalhada · vários: o que for reconhecido com segurança é gravado sozinho</small></>}
        </label>
        <div className="row" style={{ marginTop: 10 }}>
          <label className="btn sec" style={{ cursor: "pointer" }}>Importar uma pasta inteira…
            <input type="file" hidden multiple {...{ webkitdirectory: "", directory: "" } as any} onChange={e => { escolhe(e.target.files); e.target.value = ""; }} /></label>
          <label className="note" style={{ margin: 0 }}><input type="checkbox" checked={reimportar} onChange={e => setReimportar(e.target.checked)} /> reimportar arquivos já importados</label>
        </div>
        {erro && <div className="erro" style={{ marginTop: 12 }}>{erro.message}</div>}
        {ok && <div className="okmsg" style={{ marginTop: 12 }}>{ok}</div>}
      </Card>
      <Card title="Modelos padronizados" cap="Para fontes fora do SGA: planilhas com os cabeçalhos canônicos de cada conjunto">
        <table className="t plain"><tbody>{Object.entries(esq.data ?? {}).map(([k, e]) => <tr key={k}><td>{e.rotulo}</td>
          <td><a href={`/api/importacoes/modelos/${k}.xlsx`}>XLSX</a> · <a href={`/api/importacoes/modelos/${k}.csv`}>CSV</a></td></tr>)}</tbody></table>
        <div className="note">Nomes no padrão <code>AAAA.MM.DD - Tipo - Relatório</code> informam a data (quando o arquivo não tem coluna de data) e o tipo de dia (Normal, Feriado, Fechou 15h…).</div>
      </Card>
    </div>

    {fila.length > 0 && <div style={{ marginTop: 16 }}><Card title={`Importação em lote · ${fila.length} arquivos`}
      cap={`${conta("gravado")} gravados · ${conta("pulado")} já importados · ${conta("conferir")} para conferir · ${conta("erro")} recusados${rodando ? ` · ${fila.length - conta("fila") - conta("lendo")}/${fila.length} processados…` : ""}`}>
      <div className="scroll" style={{ maxHeight: 320 }}><table className="t plain"><tbody>
        {[...fila].sort((x, y) => ORDEM_ESTADO.indexOf(x.estado) - ORDEM_ESTADO.indexOf(y.estado)).map(i => <tr key={i.nome}>
          <td>{i.nome}</td><td><span className={`conf ${i.estado === "gravado" ? "alta" : i.estado === "erro" ? "baixa" : i.estado === "conferir" ? "media" : ""}`}>{i.estado}</span></td>
          <td style={{ whiteSpace: "normal" }}>{i.msg}</td>
          <td>{i.estado === "conferir" && <button className="btn sec" style={{ padding: "2px 10px" }} onClick={() => { setA(i.analise!); scrollTo(0, 0); }}>Conferir</button>}</td></tr>)}
      </tbody></table></div>
    </Card></div>}

    {a?.automatico && <div style={{ marginTop: 16 }}><Card title={<>{rot(a.conjunto)}: {a.arquivo}</>}
      cap={`Reconhecido automaticamente · ${ORIGEM[a.tipo_arquivo]}${a.de ? ` · ${a.de === a.ate ? fD(a.de) : `${fD(a.de)} a ${fD(a.ate!)}`}` : ""}${a.tipo_dia ? ` · dia: ${a.tipo_dia}` : ""}`}>
      {dup(a)}
      {a.avisos.map((x, i) => <div key={i} className="aviso" style={{ marginBottom: 8 }}>{x}</div>)}
      {a.resumo ? <table className="t plain"><tbody>{Object.entries(a.resumo).map(([k, n]) => <tr key={k}><td>{rot(k)}</td><td>{fN(n)} registros</td></tr>)}</tbody></table>
        : <><div className="okmsg">{fN(a.linhas ?? 0)} registros</div>
          {a.amostra.length > 0 && <div style={{ overflowX: "auto", marginTop: 10 }}><table className="t plain"><thead><tr>{a.colunas.map(c => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{a.amostra.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody></table></div>}</>}
      <div className="note">Os dias presentes no arquivo substituem os dados desses dias neste conjunto.</div>
      {botoes(a.linhas ?? 0)}
    </Card></div>}

    {a && !a.automatico && <div style={{ marginTop: 16 }}><Card title={<>Conferência: {a.arquivo}</>}
      cap={`${a.abas.length > 1 ? `Aba “${a.abas[a.aba].nome}” · ` : ""}cabeçalho na linha ${a.linha_cabecalho} · ${fN(a.total_linhas)} linhas${a.tipo_dia ? ` · dia: ${a.tipo_dia}` : ""}`}>
      <div className="row" style={{ marginBottom: 12 }}>
        <label className="fg">Conjunto&nbsp;<select className="inp" value={a.conjunto} onChange={e => muda({ conjunto: e.target.value })}>
          {a.ranking.map(([c, s]) => <option key={c} value={c}>{rot(c)} ({Math.round(s * 100)}%)</option>)}</select></label>
        <Conf c={a.confianca} />
        {a.abas.length > 1 && <label className="fg">Aba&nbsp;<select className="inp" value={a.aba} onChange={e => muda({ aba: +e.target.value })}>
          {a.abas.map((x, i) => <option key={i} value={i}>{x.nome} ({x.linhas})</option>)}</select></label>}
        {previa.isPending && <span className="note">atualizando…</span>}
      </div>
      {dup(a)}
      {a.avisos.map((x, i) => <div key={i} className="aviso" style={{ marginBottom: 8 }}>{x}</div>)}

      <div className="grid g2">
        <div><h3 style={{ fontSize: 14 }}>Mapeamento de colunas</h3>
          <table className="t plain"><thead><tr><th>Campo</th><th>Coluna do arquivo</th><th></th></tr></thead><tbody>
            {a.campos.map(c => <tr key={c.nome}><td><b>{c.nome}</b>{c.obrigatorio && " *"}<br /><small style={{ color: "var(--ink-3)" }}>{c.descricao}</small></td>
              <td>{c.nome === "data" && a.data_arquivo && a.mapeamento.data == null && <div className="pill" style={{ marginBottom: 4 }}>do nome do arquivo: {fD(a.data_arquivo)}</div>}
                <select className="inp" value={a.mapeamento[c.nome] ?? ""} onChange={e => muda({ mapeamento: { ...a.mapeamento, [c.nome]: e.target.value === "" ? (null as any) : +e.target.value } })}>
                <option value="">— não usar —</option>{a.colunas.map((col, j) => <option key={j} value={j}>{col}</option>)}</select>
                {c.tipo === "duracao" && a.mapeamento[c.nome] != null && <select className="inp" style={{ marginLeft: 6 }} value={a.unidades[c.nome] || "s"}
                  onChange={e => muda({ unidades: { ...a.unidades, [c.nome]: e.target.value } })}><option value="s">números em segundos</option><option value="min">números em minutos</option></select>}</td>
              <td>{a.confianca_campos[c.nome] != null && a.mapeamento[c.nome] != null && <Conf c={a.confianca_campos[c.nome]} />}</td></tr>)}
          </tbody></table></div>
        <div><h3 style={{ fontSize: 14 }}>Validação</h3>
          <div className={a.validacao.validas ? "okmsg" : "erro"}><b>{fN(a.validacao.validas)}</b> linhas válidas{a.validacao.de && <> · {fD(a.validacao.de)} a {fD(a.validacao.ate!)} ({a.validacao.dias} dias)</>}</div>
          {a.validacao.com_erro > 0 && <><div className="aviso" style={{ marginTop: 8 }}><b>{fN(a.validacao.com_erro)}</b> linhas serão descartadas (ex.: totais, linhas em branco ou valores inválidos).</div>
            <div className="scroll" style={{ maxHeight: 200, marginTop: 8 }}><table className="t plain"><thead><tr><th>Linha</th><th>Campo</th><th>Valor</th><th>Motivo</th></tr></thead>
              <tbody>{a.validacao.erros.map((e, i) => <tr key={i}><td>{e.linha}</td><td>{e.campo}</td><td>{e.valor}</td><td>{e.erro}</td></tr>)}</tbody></table></div></>}
          <div className="note">Os dias presentes no arquivo substituem os dados desses dias neste conjunto. O lote pode ser revertido depois.</div>
          {botoes(a.validacao.validas)}
        </div>
      </div>

      <h3 style={{ fontSize: 14, marginTop: 16 }}>Amostra (primeiras linhas)</h3>
      <div style={{ overflowX: "auto" }}><table className="t plain"><thead><tr>{a.colunas.map((c, j) => <th key={j} className={mapeadas.has(j) ? "map" : ""}>{c}</th>)}</tr></thead>
        <tbody>{a.amostra.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody></table></div>
    </Card></div>}

    <div style={{ marginTop: 16 }}><Card title="Histórico de importações" cap="Cada lote registra arquivo, autor, período e linhas · reverter remove as linhas do lote (não restaura dados que ele substituiu)">
      <div className="scroll"><table className="t plain"><thead><tr><th>#</th><th>Quando</th><th>Conjunto</th><th>Arquivo</th><th>Período</th><th>Linhas</th><th>Por</th><th></th></tr></thead>
        <tbody>{(lotes.data ?? []).map(b => <tr key={b.id} style={{ opacity: b.status === "ativo" ? 1 : .55 }}>
          <td>{b.id}</td><td>{fDH(b.criado_em)}</td><td>{rot(b.conjunto)}</td><td title={b.avisos.join("\n")}>{b.arquivo}</td>
          <td>{b.de ? (b.de === b.ate ? fD(b.de) : `${fD(b.de)} a ${fD(b.ate!)}`) : "–"}</td><td>{fN(b.linhas_carregadas)}</td>
          <td>{b.usuario ?? "—"}</td>
          <td>{b.status === "ativo" ? pode("dados:excluir") && <button className="btn perigo" style={{ padding: "2px 10px" }} disabled={reverte.isPending}
            onClick={() => confirm(`Reverter o lote #${b.id} (${b.arquivo})? As linhas dele serão removidas do painel.`) && reverte.mutate(b.id)}>Reverter</button>
            : <span className="pill">revertido</span>}</td></tr>)}</tbody></table></div>
    </Card></div>
  </main>;
}

/* ---------- Usuários ---------- */
type Usuario = Perfil & { ativo: boolean; criado_em: string; ultimo_acesso: string | null };
const PAPEIS: [string, string][] = [["leitor", "Leitor — consulta o painel"], ["gestor", "Gestor — importa e reverte dados"], ["admin", "Administrador — tudo, inclusive usuários"]];

export function Usuarios() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const us = useQuery({ queryKey: ["usuarios"], queryFn: () => api.get<Usuario[]>("/api/usuarios") });
  const [novo, setNovo] = useState({ email: "", nome: "", papel: "leitor", senha: "" });
  const ok = () => qc.invalidateQueries({ queryKey: ["usuarios"] });
  const cria = useMutation({ mutationFn: () => api.post("/api/usuarios", { ...novo, senha: novo.senha || null }), onSuccess: () => { ok(); setNovo({ email: "", nome: "", papel: "leitor", senha: "" }); } });
  const altera = useMutation({ mutationFn: ({ id, ...b }: { id: number } & Record<string, unknown>) => api.patch(`/api/usuarios/${id}`, b), onSuccess: ok });
  const erro = cria.error || altera.error;
  return <main><div className="grid g2">
    <Card title="Usuários" cap="Papéis definem o que cada pessoa pode fazer (RBAC) · desative em vez de excluir, para manter a auditoria">
      {erro && <div className="erro" style={{ marginBottom: 10 }}>{erro.message}</div>}
      <div className="scroll"><table className="t plain"><thead><tr><th>Nome</th><th>Papel</th><th>Login</th><th>Último acesso</th><th></th></tr></thead>
        <tbody>{(us.data ?? []).map(u => <tr key={u.id} style={{ opacity: u.ativo ? 1 : .55 }}>
          <td><b>{u.nome}</b><br /><small>{u.email}</small></td>
          <td><select className="inp" value={u.papel} onChange={e => altera.mutate({ id: u.id, papel: e.target.value })}>{PAPEIS.map(([k]) => <option key={k} value={k}>{k}</option>)}</select></td>
          <td>{[u.tem_senha && "senha", u.google && "Google"].filter(Boolean).join(" · ") || "—"}</td>
          <td>{u.ultimo_acesso ? fDH(u.ultimo_acesso) : "nunca"}</td>
          <td className="row">
            <button className="btn sec" style={{ padding: "2px 10px" }} disabled={u.id === user?.id} onClick={() => altera.mutate({ id: u.id, ativo: !u.ativo })}>{u.ativo ? "Desativar" : "Reativar"}</button>
            <button className="btn sec" style={{ padding: "2px 10px" }} onClick={() => { const s = prompt(`Nova senha para ${u.email} (mín. 10 caracteres):`); if (s) altera.mutate({ id: u.id, senha: s }); }}>Senha</button>
          </td></tr>)}</tbody></table></div>
    </Card>
    <Card title="Novo usuário" cap="Sem senha, a pessoa entra apenas com a conta Google do mesmo email">
      <form className="form" onSubmit={e => { e.preventDefault(); cria.mutate(); }}>
        <label>Nome<input required minLength={2} value={novo.nome} onChange={e => setNovo({ ...novo, nome: e.target.value })} /></label>
        <label>Email<input type="email" required value={novo.email} onChange={e => setNovo({ ...novo, email: e.target.value })} /></label>
        <label>Papel<select value={novo.papel} onChange={e => setNovo({ ...novo, papel: e.target.value })}>{PAPEIS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label>Senha inicial (opcional)<input type="password" minLength={10} autoComplete="new-password" value={novo.senha} onChange={e => setNovo({ ...novo, senha: e.target.value })} /></label>
        <button className="btn" disabled={cria.isPending}>Criar usuário</button>
      </form>
    </Card>
  </div></main>;
}

/* ---------- Auditoria ---------- */
export function Auditoria() {
  const a = useQuery({ queryKey: ["auditoria"], queryFn: () => api.get<{ id: number; quando: string; usuario: string | null; acao: string; detalhe: unknown }[]>("/api/auditoria") });
  return <main><Card title="Auditoria" cap="Últimos 200 eventos: logins, importações, reversões e mudanças de usuários">
    <div className="scroll" style={{ maxHeight: "75vh" }}><table className="t plain"><thead><tr><th>Quando</th><th>Usuário</th><th>Ação</th><th>Detalhe</th></tr></thead>
      <tbody>{(a.data ?? []).map(x => <tr key={x.id}><td>{fDH(x.quando)}</td><td>{x.usuario ?? "—"}</td><td>{x.acao}</td>
        <td style={{ whiteSpace: "normal" }}><code>{x.detalhe ? JSON.stringify(x.detalhe) : ""}</code></td></tr>)}</tbody></table></div>
  </Card></main>;
}

/* ---------- Conta ---------- */
export function Conta() {
  const { user } = useAuth();
  const [atual, setAtual] = useState(""), [nova, setNova] = useState(""), [conf, setConf] = useState("");
  const m = useMutation({ mutationFn: () => api.post("/api/auth/senha", { atual: atual || null, nova }), onSuccess: () => { setAtual(""); setNova(""); setConf(""); } });
  if (!user) return null;
  return <main><div className="grid g2">
    <Card title="Minha conta" cap={user.email}>
      <table className="t plain"><tbody><tr><td>Nome</td><td>{user.nome}</td></tr><tr><td>Perfil</td><td>{user.papel}</td></tr>
        <tr><td>Permissões</td><td style={{ whiteSpace: "normal" }}>{user.permissoes.join(", ")}</td></tr>
        <tr><td>Login Google</td><td>{user.google ? "vinculado" : "não vinculado"}</td></tr></tbody></table>
    </Card>
    <Card title={user.tem_senha ? "Trocar senha" : "Definir senha"} cap="Mínimo de 10 caracteres">
      <form className="form" onSubmit={e => { e.preventDefault(); if (nova === conf) m.mutate(); }}>
        {m.error && <div className="erro">{m.error.message}</div>}
        {m.isSuccess && <div className="okmsg">Senha atualizada.</div>}
        {user.tem_senha && <label>Senha atual<input type="password" required autoComplete="current-password" value={atual} onChange={e => setAtual(e.target.value)} /></label>}
        <label>Nova senha<input type="password" required minLength={10} autoComplete="new-password" value={nova} onChange={e => setNova(e.target.value)} /></label>
        <label>Confirmar<input type="password" required minLength={10} autoComplete="new-password" value={conf} onChange={e => setConf(e.target.value)} /></label>
        {conf && nova !== conf && <div className="aviso">As senhas não conferem.</div>}
        <button className="btn" disabled={m.isPending || nova !== conf}>Salvar</button>
      </form>
    </Card>
  </div></main>;
}
