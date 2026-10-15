# Arquitetura

```
Navegador (frontend "dummy")          Sistemas do cliente (ERP, BI)
  HTML/CSS/JS sem regra de negócio       X-API-Key ou JWT
            │  HTTPS, JSON                       │
            ▼                                    ▼
 ┌───────────────────────── FastAPI (backend/app) ─────────────────────────┐
 │ middleware: cabeçalhos de segurança, CSP, rate limit, request-id,        │
 │             contexto de auditoria                                        │
 │ routers:  auth · cadastros · juridico · documentos · relatorios          │
 │ services: cnpj · cfop · nfe · extratos · classificador (IA) ·            │
 │           investimentos · relatorios · contratos · open_finance          │
 │ audit.py: listener after_flush → tabela `auditoria` (mesma transação)    │
 └───────────────┬───────────────────────────────┬─────────────────────────┘
                 ▼                               ▼
          PostgreSQL / SQLite            Provedores externos
                                         (BrasilAPI/ReceitaWS/SERPRO, SMTP,
                                          agregador Open Finance)
 app/jobs.py (robôs): IA em lote, alertas, importação de pastas, limpeza
```

## Princípios

- **Backend como fonte da verdade.** Cálculos (DRE, fluxo, rendimentos, tributos, CFOP, IA) e regras
  de permissão estão só no servidor. O frontend nunca recebe dados de outro tenant e não decide nada:
  mesmo um frontend adulterado não contorna regras.
- **Multi-tenant por escritório.** Toda entidade de negócio tem `escritorio_id`;
  `obter_cliente_autorizado` garante o isolamento por escritório e, para o perfil `cliente`,
  pela própria empresa. Recursos de outro tenant respondem 404 (não revelam existência).
- **Perfis:** `admin` (tudo, inclusive usuários, chaves de API e auditoria), `analista` (operação),
  `cliente` (apenas a própria empresa: envio de documentos, classificação, relatórios, aceite do contrato).

## Modelo de dados (principais tabelas)

| Tabela | Conteúdo |
|---|---|
| `escritorio`, `usuario`, `cliente` | Cadastros (dados da Receita guardados em `dados_receita`) |
| `desafio_otp`, `sessao_refresh`, `chave_api` | Autenticação (somente hashes são armazenados) |
| `modelo_contrato`, `contrato` | Contrato de adesão versionado; texto e hash congelados no contrato |
| `termo_versao`, `aceite_termo` | Termos LGPD versionados e aceites com hash/IP |
| `procuracao` | Procurações com PDF, vigência e revogação |
| `plano_conta` | Plano gerencial; `grupo` define a linha da DRE (`nao_dre` = patrimonial) |
| `nota_fiscal`, `item_nota`, `duplicata` | NF-e com itens classificados e parcelas |
| `conta_bancaria`, `importacao_extrato`, `lancamento_bancario` | Extratos com deduplicação e classificação |
| `posicao_aplicacao` | Extrato mensal por produto de investimento |
| `consentimento_open_finance` | Consentimentos junto ao provedor |
| `auditoria` | Append-only: quem, quando, ação, tabela, registro, antes/depois, campos, IP, request-id |

## Regras contábeis

- **CFOP → conta** (`services/cfop.py`): o CFOP do XML é do emitente; para notas recebidas é convertido
  para a ótica do cliente (5→1, 6→2, 7→3). Vendas → receita bruta; compras para revenda/industrialização
  → custos; uso e consumo → despesas; ativo imobilizado, remessas e transferências → fora da DRE;
  devoluções de venda → deduções; devoluções de compra → redução de custos.
- **DRE gerencial** = itens de NF-e + ICMS/PIS/COFINS destacados nas vendas + lançamentos bancários em
  contas de resultado + aplicações (rendimento bruto, IRRF/IOF, taxa de administração).
  Recebimentos e pagamentos de notas devem ser classificados em 9.1.01/9.1.02 para não duplicar valores;
  a DRE informa a origem dos valores.
- **Fluxo de caixa** realizado = extratos; projetado = duplicatas das NF-e.
- **Aplicações**: rendimento líquido = saldo final − inicial − aplicações + resgates;
  bruto = líquido + IRRF + IOF + taxa de adm.; capital médio pelo método de Dietz simplificado.

## IA de classificação (`services/classificador.py`)

1. Histórico normalizado idêntico + mesma natureza já classificado pelo cliente → confiança alta;
2. Naive Bayes sobre os termos do histórico (peso 1 para o cliente, 0,3 para o restante do escritório);
3. Regras de partida a frio (tarifa, IOF, rendimento, folha, aluguel, DAS…) — só sugestões.

Somente sugestões acima de `BPO_IA_CONFIANCA_MINIMA` (0,75) são aplicadas, sempre como
`ia_sugerida`, aguardando confirmação. Tudo roda localmente: nenhum dado financeiro sai do servidor.
Um modelo de linguagem pode ser plugado no futuro para a partida a frio, desde que com contrato de
operador de dados e anonimização dos históricos.

## Evolução recomendada

- Migrações com Alembic (hoje `create_all`, idempotente);
- Armazenamento de PDFs/XML em object storage com criptografia (hoje no banco);
- NFS-e (padrão nacional), CT-e e campos de IBS/CBS da reforma tributária no parser;
- Adaptador real de Open Finance (ver `docs/open-finance.md`).
