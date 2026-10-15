# BPO Financeiro

Sistema web de **BPO Financeiro para escritórios de contabilidade**: o escritório recebe
documentos fiscais e bancários dos clientes, classifica-os (com apoio de IA) e entrega
consultoria contábil e tributária por **painéis de BI**: Fluxo de Caixa, DRE e indicadores gerenciais.

| Camada | Tecnologia | Papel |
|---|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, PostgreSQL (SQLite em dev) | **Toda** regra de negócio, cálculo, autorização e auditoria |
| API | OpenAPI 3 / Swagger em `/api/docs` (ReDoc em `/api/redoc`) | Integração com outros sistemas (JWT ou `X-API-Key`) |
| Frontend | HTML + CSS + JavaScript puro (ES modules), sem build | "Dummy": só exibe dados e envia formulários |
| Robôs (RPA) | `python -m app.jobs` | IA em lote, alertas, importação de pastas, limpeza |

## Funcionalidades

1. **Login com OTP por e-mail** (senha + código de 6 dígitos), troca e recuperação de senha,
   bloqueio após tentativas, refresh token rotativo com detecção de reuso.
2. **Cadastros**
   - Escritório: cadastro pelo CNPJ com importação dos dados oficiais (razão social, endereço, CNAE, situação).
     Razão social, CNPJ, CRC e responsável técnico aparecem como **"Elaborado por"** em todos os relatórios.
   - Clientes: mesma importação pelo CNPJ. Aceita o **CNPJ alfanumérico** (IN RFB 2.229/2024, vigente desde jul/2026).
   - **Contrato de adesão** de BPO Financeiro: modelo versionado com variáveis, emissão por cliente e
     **aceite eletrônico** pelo representante (data/hora, IP, user-agent e hash SHA-256 do texto aceito).
3. **LGPD e confidencialidade**: Termos de Uso, Política de Privacidade e Termo de Confidencialidade
   versionados, com aceite obrigatório (nova versão exige novo aceite) e relatório de comprovação;
   portabilidade de dados (art. 18, V); **procurações** (e-CAC, SEFAZ, prefeitura…) com PDF, vigência e alertas de vencimento.
4. **Repositório de documentos**
   - **NF-e emitidas e recebidas (XML ou ZIP)**: o sistema identifica se a nota é emitida ou recebida,
     evita duplicidade pela chave e **classifica cada item pelo CFOP** (convertendo para a ótica do cliente:
     5102 do fornecedor → 1102 compra para revenda). Itens podem ser reclassificados.
   - **Extratos de conta corrente (OFX/CSV)**: o cliente classifica os primeiros lançamentos pelo
     histórico e natureza (débito/crédito); a classificação é replicada aos semelhantes e a **IA**
     aprende e classifica os próximos extratos (sugestões revisáveis, com nível de confiança).
   - **Extratos de aplicações**: rendimento bruto e líquido, taxa mensal e anual equivalente, % do CDI,
     taxa de administração, IRRF/IOF e alíquota efetiva; simulador da tabela regressiva.
   - **Open Finance**: arquitetura pronta com consentimento e sincronização (provedor simulado incluído);
     ver a análise de viabilidade em [`docs/open-finance.md`](docs/open-finance.md).
5. **Relatórios**: Fluxo de Caixa (realizado e projetado pelas duplicatas das NF-e), DRE gerencial mensal
   com detalhamento por conta e origem dos valores, relatório gerencial (margens, ticket médio, saldo,
   contas a receber/pagar, maiores clientes/fornecedores/despesas, alertas). Exportação CSV e impressão/PDF.
6. **Segurança e API**: veja [`docs/seguranca-lgpd.md`](docs/seguranca-lgpd.md). Trilha de auditoria
   automática (quem, quando, o que mudou, com valores antes/depois) em `GET /api/v1/auditoria`.
7. **UX e acessibilidade (WCAG 2.1 AA)**: rótulos e ids em todos os controles, botões de ícone com nomes
   específicos ("Excluir nota 123 de ACME"), estados com texto (selos), foco visível, contraste verificado,
   navegação por teclado (abas no padrão WAI-ARIA), erros associados aos campos (`aria-describedby` +
   resumo com links), operações impossíveis desabilitadas com explicação e CTA, cartões no mobile e
   barra de ações fixa. Uma auditoria automatizada roda no teste E2E em cada tela.

## Como executar

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
BPO_COOKIE_SEGURO=false uvicorn app.main:app --reload
```

Acesse http://localhost:8000 (frontend) e http://localhost:8000/api/docs (Swagger).
Sem SMTP configurado, o código OTP aparece no log do servidor (somente fora de produção).

Com Docker (PostgreSQL + API + robôs):

```bash
export BPO_JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
docker compose up --build
```

### Deploy no Render

O arquivo [`render.yaml`](render.yaml) é um *Blueprint*: cria o serviço web (Docker) e o PostgreSQL.

1. No Render: **New → Blueprint** e selecione este repositório (branch `main`).
2. Preencha as variáveis marcadas como *sync: false*: `BPO_SMTP_HOST`, `BPO_SMTP_USUARIO`,
   `BPO_SMTP_SENHA` e `BPO_SMTP_REMETENTE`. **Sem SMTP ninguém consegue entrar**, porque o login exige o código OTP por e-mail.
3. `BPO_JWT_SECRET` é gerado automaticamente; HTTPS, HSTS e cookies `Secure` já vêm ativos.
4. Após o deploy, acesse `https://<seu-servico>.onrender.com/#/cadastro` e cadastre o escritório.

Os planos `free` do blueprint servem para avaliação: o serviço hiberna sem uso e o Postgres free expira
em 30 dias. Em produção, use planos pagos (o banco ganha backups) e descomente o *cron job* dos robôs.

Configurações: variáveis `BPO_*` (ver [`.env.example`](.env.example) e `backend/app/config.py`).

## Testes (QA)

```bash
cd backend
python -m pytest -q                 # unitários + API + E2E
pip install playwright && python -m playwright install chromium   # habilita o E2E
E2E_SCREENSHOTS=/tmp/telas python -m pytest tests/test_e2e.py     # salva screenshots das telas
```

A suíte cobre: OTP, bloqueio, rotação/reuso de refresh, troca e recuperação de senha, anti-enumeração,
isolamento entre escritórios e entre clientes, chaves de API, auditoria, CNPJ (inclusive alfanumérico),
CFOP, importação de NF-e (duplicidade, notas de terceiros, canceladas, XXE, ZIP), OFX/CSV, IA de
classificação, aplicações e tributos, DRE, Fluxo de Caixa, CSV, contratos, termos, procurações,
cabeçalhos de segurança, autenticação obrigatória em todas as rotas e o fluxo completo no navegador.

## Robôs (RPA)

```bash
python -m app.jobs diario                 # IA nos pendentes + alertas por e-mail + limpeza
python -m app.jobs importar-pasta /dados  # /dados/<CNPJ do cliente>/*.xml|*.zip|<id_conta>_*.ofx
```

`importar-pasta` permite que robôs de captura (portal da SEFAZ, caixa de e-mail, SFTP do banco)
apenas depositem arquivos; o sistema importa, classifica e move para `processados/`.

## Documentação

- [Arquitetura e modelo de dados](docs/arquitetura.md)
- [Segurança, SRE e LGPD](docs/seguranca-lgpd.md)
- [Open Finance: viabilidade e plano](docs/open-finance.md)
