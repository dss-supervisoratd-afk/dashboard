"""Layout padronizado de cada conjunto importável.

Cada campo tem um nome canônico (cabeçalho dos modelos para download), um tipo e
sinônimos usados no reconhecimento automático de colunas de planilhas e PDFs.
Sinônimos são comparados já normalizados (minúsculas, sem acentos, só [a-z0-9 ]).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Campo:
    nome: str
    tipo: str  # data | datahora | hora | inteiro | texto | duracao
    obrigatorio: bool
    sinonimos: tuple[str, ...]
    descricao: str = ""


@dataclass(frozen=True)
class Esquema:
    nome: str
    rotulo: str
    campos: tuple[Campo, ...]
    dicas_arquivo: tuple[str, ...] = ()  # trechos do nome do arquivo que indicam o conjunto
    # grupos em que basta um dos campos (ex.: data OU data_hora)
    alternativos: tuple[tuple[str, ...], ...] = field(default=())

    def campo(self, nome: str) -> Campo:
        return next(c for c in self.campos if c.nome == nome)


_DATA = ("data", "dt", "dia", "data registro", "data de registro", "data abertura", "data de abertura",
         "data da mensagem", "data recebimento", "data atendimento", "data do atendimento", "criado em",
         "data criacao", "data de criacao", "data emissao")

ESQUEMAS: dict[str, Esquema] = {
    "ouvidoria": Esquema("ouvidoria", "Ouvidoria (remoto)", (
        Campo("data", "data", True, _DATA, "Dia da mensagem"),
        Campo("setor", "texto", True, ("setor", "area", "departamento", "categoria", "grupo", "assunto",
                                       "setor responsavel", "area responsavel"), "Setor de destino"),
        Campo("subsetor", "texto", False, ("subsetor", "sub setor", "subarea", "sub area", "subcategoria",
                                           "sub categoria", "subassunto", "sub assunto", "produto", "convenio",
                                           "item", "detalhe"), "Subsetor, produto ou convênio"),
        Campo("qtd", "inteiro", False, ("qtd", "qtde", "quantidade", "total", "mensagens", "volume", "count",
                                        "numero de mensagens", "n"), "Quantidade (padrão 1 por linha)"),
    ), dicas_arquivo=("ouvid", "ouv")),
    "atendimentos": Esquema("atendimentos", "Atendimentos concluídos", (
        Campo("data", "data", True, _DATA, "Dia do atendimento"),
        Campo("data_hora", "datahora", False, ("data hora", "data e hora", "inicio", "inicio atendimento",
                                               "inicio da chamada", "hora chamada", "chamada", "data chamada",
                                               "emissao senha", "data hora chamada"), "Início (data e hora)"),
        Campo("hora", "hora", False, ("hora", "hr", "hora inicio", "hora da chamada", "faixa horaria"), "Hora (0–23)"),
        Campo("servico", "texto", True, ("servico", "servico triado", "tipo servico", "tipo de servico", "fila",
                                         "assunto", "servico solicitado"), "Serviço triado"),
        Campo("atendente", "texto", True, ("atendente", "usuario", "guiche", "colaborador", "funcionario",
                                           "atendido por", "responsavel", "operador"), "Atendente ou guichê"),
        Campo("dur", "duracao", False, ("duracao", "tempo atendimento", "tempo de atendimento", "dur",
                                        "tempo"), "Duração do atendimento"),
        Campo("perm", "duracao", False, ("permanencia", "tempo permanencia", "tempo de permanencia", "perm",
                                         "tempo total", "tempo na unidade"), "Permanência total"),
    ), dicas_arquivo=("conclu", "atendimentos"), alternativos=(("data", "data_hora"),)),
    "servicos": Esquema("servicos", "Serviços executados", (
        Campo("data", "data", True, _DATA, "Dia da execução"),
        Campo("servico", "texto", True, ("servico", "servico executado", "servicos executados", "descricao",
                                         "tipo servico", "tipo de servico"), "Serviço executado"),
        Campo("qtd", "inteiro", False, ("qtd", "qtde", "quantidade", "total", "executados", "n"),
              "Quantidade (padrão 1 por linha)"),
    ), dicas_arquivo=("execut", "presenc")),
    "tempos": Esquema("tempos", "Tempos por atendente (TMA)", (
        Campo("data", "data", True, _DATA, "Dia"),
        Campo("atendente", "texto", True, ("atendente", "usuario", "guiche", "colaborador", "funcionario",
                                           "operador"), "Atendente ou guichê"),
        Campo("n", "inteiro", True, ("atendimentos", "qtd", "qtde", "quantidade", "total atendimentos",
                                     "n", "numero atendimentos", "senhas"), "Nº de atendimentos"),
        Campo("tme", "duracao", False, ("tme", "tempo medio espera", "tempo medio de espera", "espera",
                                        "media espera"), "Tempo médio de espera"),
        Campo("tmd", "duracao", False, ("tmd", "tempo medio deslocamento", "tempo medio de deslocamento",
                                        "deslocamento"), "Tempo médio de deslocamento"),
        Campo("tma", "duracao", False, ("tma", "tempo medio atendimento", "tempo medio de atendimento",
                                        "media atendimento"), "Tempo médio de atendimento"),
        Campo("tot", "duracao", False, ("tempo total", "tmt", "tempo medio total", "permanencia media",
                                        "total"), "Tempo médio total"),
    ), dicas_arquivo=("tma", "tempo")),
    "calendario": Esquema("calendario", "Calendário (tipo de dia)", (
        Campo("data", "data", True, _DATA, "Dia"),
        Campo("tipo", "texto", True, ("tipo", "tipo dia", "tipo de dia", "classificacao", "feriado", "evento",
                                      "descricao", "ocorrencia"), "Ex.: Feriado, Ponto facultativo, Normal"),
    ), dicas_arquivo=("calend", "feriad")),
}
