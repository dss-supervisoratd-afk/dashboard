"""Modelo dimensional: dim_dia (calendário) + quatro tabelas de fatos, todas ligadas
ao lote de importação que as carregou (linhagem e reversão)."""
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))
    papel: Mapped[str] = mapped_column(String(20), default="leitor")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    senha_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base):
    __tablename__ = "lote_importacao"
    id: Mapped[int] = mapped_column(primary_key=True)
    conjunto: Mapped[str] = mapped_column(String(30), index=True)
    arquivo: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ativo")  # ativo | revertido
    linhas_lidas: Mapped[int] = mapped_column(Integer, default=0)
    linhas_carregadas: Mapped[int] = mapped_column(Integer, default=0)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    mapeamento: Mapped[dict | None] = mapped_column(JSON)
    avisos: Mapped[list | None] = mapped_column(JSON)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Dia(Base):
    __tablename__ = "dim_dia"
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    ano_mes: Mapped[str] = mapped_column(String(7), index=True)
    dia_semana: Mapped[int] = mapped_column(SmallInteger)  # 0 = domingo (igual ao JS)
    tipo: Mapped[str] = mapped_column(String(40))  # rótulo final usado nos filtros
    tipo_origem: Mapped[str | None] = mapped_column(String(40))  # vindo do calendário importado


class FOuvidoria(Base):
    __tablename__ = "f_ouvidoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(ForeignKey("dim_dia.data"), index=True)
    setor: Mapped[str] = mapped_column(String(120), index=True)
    subsetor: Mapped[str] = mapped_column(String(160))
    qtd: Mapped[int] = mapped_column(Integer)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote_importacao.id"), index=True)


class FServico(Base):
    __tablename__ = "f_servico"
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(ForeignKey("dim_dia.data"), index=True)
    servico: Mapped[str] = mapped_column(String(160), index=True)
    qtd: Mapped[int] = mapped_column(Integer)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote_importacao.id"), index=True)


class FTempo(Base):
    __tablename__ = "f_tempo"
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(ForeignKey("dim_dia.data"), index=True)
    atendente: Mapped[str] = mapped_column(String(160), index=True)
    # rótulo cru do SGA ("guiche 18", "sala 1"); atendente é o nome resolvido pelo cadastro de guichês
    atendente_origem: Mapped[str | None] = mapped_column(String(160))
    n: Mapped[int] = mapped_column(Integer)
    # médias em segundos
    tme: Mapped[float | None] = mapped_column(Float)
    tmd: Mapped[float | None] = mapped_column(Float)
    tma: Mapped[float | None] = mapped_column(Float)
    tot: Mapped[float | None] = mapped_column(Float)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote_importacao.id"), index=True)


class FAtendimento(Base):
    __tablename__ = "f_atendimento"
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(ForeignKey("dim_dia.data"), index=True)
    hora: Mapped[int | None] = mapped_column(SmallInteger)
    servico: Mapped[str] = mapped_column(String(160), index=True)
    atendente: Mapped[str] = mapped_column(String(160), index=True)
    atendente_origem: Mapped[str | None] = mapped_column(String(160))
    dur: Mapped[int | None] = mapped_column(Integer)  # segundos
    perm: Mapped[int | None] = mapped_column(Integer)  # segundos
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote_importacao.id"), index=True)


class CadGuiche(Base):
    """Cadastro "Guichês - Tabela Consolidada": quem ocupa cada guichê/sala e desde quando."""
    __tablename__ = "cad_guiche"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))  # guiche | sala
    numero: Mapped[int] = mapped_column(Integer, index=True)
    atendente: Mapped[str] = mapped_column(String(160))
    grupo: Mapped[str] = mapped_column(String(80), default="")
    vig_inicio: Mapped[date | None] = mapped_column(Date)
    vig_fim: Mapped[date | None] = mapped_column(Date)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote_importacao.id"))


class Auditoria(Base):
    __tablename__ = "auditoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    acao: Mapped[str] = mapped_column(String(60), index=True)
    detalhe: Mapped[dict | None] = mapped_column(JSON)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)


FATOS = {"ouvidoria": FOuvidoria, "servicos": FServico, "tempos": FTempo, "atendimentos": FAtendimento}
