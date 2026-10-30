# Gestão do Atendimento · AMN

Sistema de gestão estratégica do atendimento ao associado. É a evolução do painel HTML
autocontido (`.resources/Painel de Atendimento.html`) para uma aplicação com banco de dados,
importação de relatórios, login e controle de acesso.

- **Backend**: FastAPI, SQLAlchemy e Postgres (SQLite em desenvolvimento e nos testes)
- **Frontend**: React, Vite e TypeScript. Os gráficos SVG do painel original foram portados como componentes, sem biblioteca de gráficos
- **Implantação**: `docker compose` (Postgres, API e nginx servindo o SPA e repassando `/api`)

## Subir com Docker

```sh
cp .env.example .env      # preencha POSTGRES_PASSWORD, SECRET_KEY, ADMIN_EMAIL e ADMIN_PASSWORD
docker compose up -d --build
```

Acesse `http://localhost:8080` com o administrador definido no `.env`. Ele é criado na
primeira inicialização, se o banco não tiver usuários.

Para carregar os dados, use **Importar dados → Importar uma pasta inteira** e escolha a pasta
`Relatórios` do repositório Estatisticas-ATD. A mesma operação pode ser feita pela CLI:

```sh
docker compose cp "Estatisticas-ATD/Relatórios" api:/tmp/relatorios
docker compose exec api python -m app.cli importar /tmp/relatorios --autor admin@amn.org.br
```

O painel HTML antigo (`Painel de Atendimento.html`) também é aceito pela tela ou pela CLI.

## Desenvolvimento

```sh
# backend (porta 8000), SQLite em backend/dev.db
cd backend
pip install -r requirements.txt pytest
ADMIN_EMAIL=admin@amn.local ADMIN_PASSWORD=admin-local-123 uvicorn app.main:app --reload

# frontend (porta 5173, com proxy de /api para :8000)
cd frontend
npm install
npm run dev
```

Testes e verificação de tipos:

```sh
cd backend && pytest                              # todos
cd backend && pytest tests/test_api.py -k rbac    # um teste
cd frontend && npm run typecheck
```

`tests/test_api.py::test_totais_batem_com_o_painel_legado` confere os totais da API com o
`RAW` do painel antigo. Esse teste é pulado quando `.resources/` não existe.

## Perfis (RBAC)

| Papel | Pode |
|---|---|
| **leitor** | consultar o painel |
| **gestor** | o mesmo que leitor, mais importar e reverter lotes e ver a auditoria |
| **admin** | tudo, inclusive gerenciar usuários e papéis |

O sistema aceita login por email e senha (argon2) e login com Google (OpenID Connect).
Uma conta Google entra quando o email já está cadastrado ou quando o domínio está em
`GOOGLE_ALLOWED_DOMAINS`; nesse segundo caso, a conta recebe o papel `GOOGLE_DEFAULT_ROLE`.
Para configurar o Google, crie um *OAuth client* do tipo "Web application" no Google Cloud
Console e cadastre a URI de redirecionamento `<FRONTEND_URL>/api/auth/google/callback`.

## Importação de dados

### Fontes reconhecidas automaticamente

| Arquivo | O que o sistema faz |
|---|---|
| `AAAA.MM.DD - Tipo - Atendimentos concluídos.pdf` (Novo SGA) | Lê um ticket por bloco da tabela: hora da chamada, serviço triado, guichê, duração e permanência |
| `… Serviços executados.pdf` | Lê os serviços executados no dia e confere a soma com o "Total:" do relatório |
| `… Tempos médios por Atendente.pdf` | Lê TME, TMD, TMA e o tempo total por usuário; descarta a sala 7 (CPD) |
| `AAAA.MM.DD [- Tipo -] Ouvidorias.xls` | Lê Setor, SubSetor e Mensagens; a data vem do nome do arquivo |
| `Guichês - Tabela Consolidada.xlsx` | Substitui o cadastro e renomeia o histórico: "guiche 18" vira "Aline (MAPMA) — guiche 18", respeitando a vigência |

O **tipo de dia** (Normal, Feriado, Fechou 15h…) vem do nome do arquivo. O consolidado
"Ouvidorias por Situação" é recusado de propósito: ele traz nomes de associados e não é
fonte do painel. Relatórios exportados com período de vários dias também são recusados,
porque o painel precisa dos valores de cada dia.

Na importação em massa, pela tela ou pela CLI, só entra sem conferência o que for
reconhecido com segurança: PDFs do SGA, o cadastro de guichês, o painel legado e planilhas
com data no nome, confiança alta e campos obrigatórios mapeados. O restante fica listado
com o botão **Conferir**.

### Outras fontes (conferência)

1. **Envio**: CSV, XLSX, XLS, PDF com tabela ou o painel HTML legado.
2. **Reconhecimento**: o sistema acha a linha de cabeçalho, sugere o conjunto (Ouvidoria,
   Atendimentos, Serviços, Tempos/TMA ou Calendário) e mapeia as colunas. A sugestão combina
   os sinônimos do cabeçalho (`backend/app/importers/schemas.py`) com o tipo dos valores
   encontrados, e cada sugestão mostra seu grau de confiança.
3. **Conferência**: você pode ajustar o conjunto, a aba, cada coluna e a unidade das durações
   numéricas (segundos ou minutos). A tela mostra a prévia, as linhas válidas e as linhas que
   serão descartadas, com o motivo.
4. **Gravação em lote**: os dias presentes no arquivo substituem os dados desses dias naquele
   conjunto, então reimportar o mesmo relatório não duplica nada. Cada lote registra arquivo,
   autor, período e mapeamento, e pode ser revertido.

A tela de importação oferece **modelos padronizados** (XLSX ou CSV) com os cabeçalhos canônicos.

## Pendências conhecidas

- As regras de leitura foram reconstruídas a partir de `Scripts/gerar_relatorio_atendimento.py`
  do repositório Estatisticas-ATD, já que o `gerar_dashboard_dados.py` original não foi encontrado.

**Próximos passos**: migrações com Alembic, verificação de prontidão (comparar os diários de
Ouvidoria com o consolidado por protocolo, sem gravar dados pessoais), metas e indicadores
estratégicos com semáforo, alertas, e reversão de lote que restaura os dados substituídos.
