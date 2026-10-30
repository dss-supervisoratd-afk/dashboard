import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// em desenvolvimento a API roda em :8000; o proxy mantém frontend e API na mesma origem (cookies SameSite)
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: process.env.API_URL || "http://localhost:8000", changeOrigin: false } } },
});
