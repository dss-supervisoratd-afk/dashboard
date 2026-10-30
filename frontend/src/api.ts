// Cliente da API: mesma origem (proxy do Vite/nginx), cookie de sessão httpOnly e
// cabeçalho anti-CSRF exigido pelo backend em métodos de escrita.
export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) { super(message); }
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const r = await fetch(url, {
    method, credentials: "same-origin",
    headers: { "X-Requested-With": "amn", ...(body && !isForm ? { "Content-Type": "application/json" } : {}) },
    body: body == null ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (!r.ok) {
    let detail: any = null;
    try { detail = await r.json(); } catch { /* resposta sem JSON */ }
    const msg = typeof detail?.detail === "string" ? detail.detail
      : Array.isArray(detail?.detail) ? detail.detail.map((d: any) => d.msg).join("; ") : `Erro ${r.status}`;
    if (r.status === 401 && !url.startsWith("/api/auth/")) window.dispatchEvent(new Event("amn:sessao-expirada"));
    throw new ApiError(r.status, msg, detail);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export const api = {
  get: <T>(u: string) => req<T>("GET", u),
  post: <T>(u: string, b?: unknown) => req<T>("POST", u, b ?? {}),
  patch: <T>(u: string, b: unknown) => req<T>("PATCH", u, b),
  del: <T>(u: string) => req<T>("DELETE", u),
};

/* ---------- tipos ---------- */
export type Perfil = { id: number; email: string; nome: string; papel: "admin" | "gestor" | "leitor"; permissoes: string[]; tem_senha: boolean; google: boolean };

export type Fonte = { rotulo: string; de: string | null; ate: string | null; linhas: number; ultima_importacao: string | null };
export type Meta =
  | { vazio: true; fontes: Record<string, Fonte> }
  | { vazio: false; de: string; ate: string; meses: string[]; parcial: string | null; tipos: [string, number][];
      setores: string[]; servicos: string[]; atendentes: string[]; fontes: Record<string, Fonte> };
export type MetaCheia = Extract<Meta, { vazio: false }>;

export type Filtros = { de?: string; ate?: string; tipo?: string; setor?: string; subsetor?: string; servico?: string; atendente?: string };
export type Consulta = { conjunto: string; dims?: string[]; medidas: string[]; filtros?: Filtros; ignorar?: string[]; ordem?: string[]; limite?: number };
export type Resultado = { colunas: string[]; linhas: any[][] };
export type Row = Record<string, any>;

export const linhas = (r: Resultado | undefined): Row[] =>
  r ? r.linhas.map(l => Object.fromEntries(r.colunas.map((c, i) => [c, l[i]]))) : [];
