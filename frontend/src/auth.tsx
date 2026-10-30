import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";
import { api, ApiError, type Perfil } from "./api";

type Ctx = { user: Perfil | null; carregando: boolean; pode: (perm: string) => boolean; sair: () => Promise<void>; recarregar: () => void };
const AuthCtx = createContext<Ctx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["me"], retry: false, staleTime: 5 * 60_000,
    queryFn: () => api.get<Perfil>("/api/auth/me").catch(e => { if (e instanceof ApiError && e.status === 401) return null; throw e; }),
  });
  useEffect(() => {
    const h = () => qc.setQueryData(["me"], null);
    window.addEventListener("amn:sessao-expirada", h);
    return () => window.removeEventListener("amn:sessao-expirada", h);
  }, [qc]);
  const user = q.data ?? null;
  const ctx: Ctx = {
    user, carregando: q.isLoading,
    pode: p => !!user?.permissoes.includes(p),
    sair: async () => { await api.post("/api/auth/logout"); qc.clear(); qc.setQueryData(["me"], null); },
    recarregar: () => qc.invalidateQueries({ queryKey: ["me"] }),
  };
  return <AuthCtx.Provider value={ctx}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

export function Protegido({ perm, children }: { perm?: string; children: ReactNode }) {
  const { user, carregando, pode } = useAuth();
  const loc = useLocation();
  if (carregando) return <div className="empty">Carregando…</div>;
  if (!user) return <Navigate to="/login" replace state={{ de: loc.pathname + loc.search }} />;
  if (perm && !pode(perm)) return <main><div className="card empty">Seu perfil ({user.papel}) não tem acesso a esta área.</div></main>;
  return <>{children}</>;
}
