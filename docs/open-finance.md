# Importação de extratos via Open Finance: viabilidade

## Conclusão

**É viável, mas não diretamente.** Receber dados de contas pelo Open Finance Brasil exige ser
instituição autorizada pelo Banco Central e participante do Diretório de Participantes (com
certificados ICP-Brasil, FAPI/mTLS e certificação de conformidade). Um escritório de contabilidade
não se enquadra. O caminho prático é contratar um **agregador/iniciador autorizado** que já é
receptor de dados e expõe uma API simples, por exemplo Pluggy, Belvo, Celcoin, Klavi ou Quanto.
Compare preço por conexão, cobertura de bancos e dados de investimentos antes de escolher.

## Como funciona

1. O escritório cria um **consentimento** para o cliente (CNPJ) com as permissões:
   `ACCOUNTS_READ`, `ACCOUNTS_BALANCES_READ`, `ACCOUNTS_TRANSACTIONS_READ`,
   `BANK_FIXED_INCOMES_READ`, `FUNDS_READ` (as duas últimas cobrem aplicações).
2. O representante do cliente é redirecionado ao app/internet banking e **autoriza** (PJ pode exigir
   aprovação de mais de um representante, conforme as alçadas do banco).
3. Com o consentimento autorizado (validade de até 12 meses, renovável), o sistema **sincroniza** as
   transações, que seguem o mesmo fluxo dos extratos OFX: deduplicação, IA e classificação.

## O que já está pronto no código

- Interface `ProvedorOpenFinance` (`backend/app/services/open_finance.py`) com
  `criar_consentimento`, `status_consentimento` e `transacoes`;
- Tabela `consentimento_open_finance`, rotas `/api/v1/open-finance/*` e botão na aba de extratos
  (desabilitado com explicação enquanto não houver provedor);
- Provedor `simulado` (`BPO_OPEN_FINANCE_PROVEDOR=simulado`) para homologar o fluxo ponta a ponta.

## Para ativar com um provedor real

1. Contratar o agregador e obter `client_id`/`client_secret` (`BPO_OPEN_FINANCE_CLIENT_ID/SECRET`);
2. Implementar o adaptador (cerca de 150 linhas): autenticação, criação do *connect token*/consentimento,
   webhook de status e paginação das transações, mapeando para `LancamentoLido` com o `FITID` do provedor;
3. Registrar o agregador como suboperador na política de privacidade e no contrato (LGPD);
4. Agendar a sincronização diária no robô (`app/jobs.py`).

Enquanto isso, a importação por **OFX/CSV** e pela pasta monitorada (`importar-pasta`) cobre 100% dos bancos.
