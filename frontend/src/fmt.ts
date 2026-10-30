// Formatadores pt-BR (portados do painel HTML original).
const NF = new Intl.NumberFormat("pt-BR");
const N1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const ok = (v: unknown): v is number => v != null && !isNaN(v as number);

export const fN = (v: number | null | undefined) => ok(v) ? NF.format(Math.round(v)) : "–";
export const f1 = (v: number | null | undefined) => ok(v) ? N1.format(v) : "–";
export const fT = (s: number | null | undefined) => {
  if (!ok(s)) return "–";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
};
export const fD = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;
export const fDs = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
export const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
export const fM = (m: string) => `${MES[+m.slice(5, 7) - 1]}/${m.slice(2, 4)}`;
export const WD = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
export const fDH = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

const SMALL = new Set(["de", "da", "do", "das", "dos", "e", "a", "o"]);
const SIGLAS = new Set(["amn", "ares", "eacr", "nit", "cg"]);
export const tc = (s: string) => String(s).toLowerCase().split(" ").map((w, i) => i && SMALL.has(w) ? w
  : w.split("-").map(x => SIGLAS.has(x) ? x.toUpperCase() : x.charAt(0).toUpperCase() + x.slice(1)).join("-")).join(" ");

export const sum = <T,>(a: T[], f: (x: T) => number) => a.reduce((t, x) => t + (f(x) || 0), 0);
export const pct = (c: number | null | undefined, p: number | null | undefined) => (c != null && p) ? (c - p) / p * 100 : null;

export const iso = (d: Date) => d.toISOString().slice(0, 10);
export const addDias = (s: string, n: number) => { const d = new Date(s + "T12:00:00"); d.setDate(d.getDate() + n); return iso(d); };
export const fimDoMes = (m: string) => { const [y, mo] = m.split("-").map(Number); return `${m}-${String(new Date(y, mo, 0).getDate()).padStart(2, "0")}`; };
export const diaSemana = (s: string) => new Date(s + "T12:00:00").getDay();
