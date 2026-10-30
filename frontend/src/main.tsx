import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiError } from "./api";
import { AuthProvider, Protegido } from "./auth";
import { Auditoria, Conta, Importar, Login, Usuarios } from "./pages";
import { PainelLayout, Shell } from "./shell";
import { Tooltip } from "./tip";
import { Dados, Equipe, Geral, Ouvidoria, Presencial } from "./views";
import "./styles.css";

const qc = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Protegido><Shell /></Protegido>}>
              <Route element={<Protegido perm="painel:ver"><PainelLayout /></Protegido>}>
                <Route index element={<Geral />} />
                <Route path="ouvidoria" element={<Ouvidoria />} />
                <Route path="presencial" element={<Presencial />} />
                <Route path="equipe" element={<Equipe />} />
                <Route path="dados" element={<Dados />} />
              </Route>
              <Route path="importar" element={<Protegido perm="dados:importar"><Importar /></Protegido>} />
              <Route path="usuarios" element={<Protegido perm="usuarios:gerir"><Usuarios /></Protegido>} />
              <Route path="auditoria" element={<Protegido perm="auditoria:ver"><Auditoria /></Protegido>} />
              <Route path="conta" element={<Conta />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
          <Tooltip />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
