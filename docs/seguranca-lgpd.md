# Segurança, SRE e LGPD

## Por que frontend "dummy"

O navegador é território do atacante. Por isso o frontend só renderiza o que a API devolve e envia
formulários: não há cálculo, regra de permissão nem segredo no cliente. Mesmo com o JavaScript
adulterado, o backend valida tudo de novo (Pydantic), autoriza cada recurso e isola os tenants.

## Controles implementados

| Ameaça | Controle |
|---|---|
| Roubo de senha / credential stuffing | Argon2id; política de senha forte; **MFA por OTP** de e-mail (6 dígitos, 10 min, 5 tentativas, uso único); bloqueio temporário após 5 falhas; rate limit por IP nas rotas de autenticação |
| Enumeração de usuários | Mesma resposta para e-mail inexistente no login e na recuperação; hash fictício para igualar o tempo de resposta |
| Sequestro de sessão | Access token JWT de 15 min, guardado só em memória; refresh em cookie `HttpOnly; Secure; SameSite=Strict` restrito a `/api/v1/auth`; **rotação** a cada uso e **revogação de todas as sessões** se um refresh antigo for reutilizado; troca de senha invalida todos os tokens (`versao_token`) |
| CSRF | Bearer token nas rotas de negócio; refresh exige `SameSite=Strict` e o cabeçalho `X-Requested-With: fetch` |
| XSS | CSP `default-src 'self'` sem `unsafe-inline`; o frontend só usa `textContent` (nunca `innerHTML`) com dados da API |
| Clickjacking, sniffing | `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, HSTS em produção |
| IDOR / vazamento entre clientes | Toda consulta passa por `obter_cliente_autorizado`; recursos alheios respondem 404 |
| XXE / billion laughs | XML lido com `defusedxml` (DTD proibida) |
| Zip bomb / upload malicioso | Limites de tamanho por arquivo, quantidade e volume descompactado; procurações só PDF (assinatura `%PDF-`) |
| CSV injection | Exportações neutralizam células que começam com `= + - @` |
| Vazamento de erro | Handler global devolve mensagem genérica + `X-Request-ID` para correlação no log |
| Chaves de integração | `X-API-Key` aleatória de 256 bits, exibida uma vez, só o hash SHA-256 é armazenado, revogável, com registro de último uso |
| Repúdio | Trilha de auditoria automática na mesma transação; logins, falhas, aceites, exportações e consultas à própria auditoria também são registrados |

Testes automatizados verificam que **todas** as rotas não públicas exigem autenticação, que tokens
adulterados ou assinados com outra chave são rejeitados, os cabeçalhos de segurança e os casos acima.

## Auditoria

`auditoria` guarda: escritório, usuário (id e e-mail), ação (`INSERT/UPDATE/DELETE` ou evento de
negócio), tabela, id do registro, valores antes e depois, campos alterados, IP, user-agent, request-id e
data/hora (UTC). Campos sensíveis (`senha_hash`, hashes de token) são mascarados e conteúdos volumosos
(XML, PDF) omitidos. Em produção (PostgreSQL), reforce a imutabilidade:

```sql
REVOKE UPDATE, DELETE, TRUNCATE ON auditoria FROM bpo_app;
-- ou um trigger que rejeite UPDATE/DELETE na tabela auditoria
```

## Checklist de produção (SRE)

- TLS no proxy reverso/WAF; `BPO_AMBIENTE=producao` (ativa HSTS e exige `BPO_JWT_SECRET` forte);
- Segredos via cofre (Vault, Secrets Manager), nunca no repositório;
- PostgreSQL com criptografia em repouso, backups diários testados e PITR;
- Rate limit distribuído (Redis ou gateway) quando houver mais de uma réplica;
- Logs centralizados com o `X-Request-ID`; alertas para picos de `LOGIN_FALHA` e `REFRESH_REUTILIZADO`;
- `pip-audit` no CI (já configurado) e atualização mensal de dependências;
- Healthcheck em `/api/saude`; contêiner sem root (já configurado no Dockerfile).

## LGPD

- **Papéis:** o cliente é o controlador e o escritório é o operador (cláusula 7ª do contrato de adesão).
- **Bases legais:** execução de contrato e cumprimento de obrigação legal (art. 7º, II e V).
- **Transparência e aceite:** termos versionados com hash; nova versão exige novo aceite; relatório de aceites.
- **Direitos do titular:** exportação estruturada (`/clientes/{id}/exportar-dados`); correção pelos cadastros;
  inativação lógica de cliente (dados fiscais mantidos pelo prazo legal de guarda).
- **Minimização:** só os dados necessários ao BPO; históricos bancários processados localmente pela IA.
- **Incidentes:** trilha de auditoria e request-id permitem apurar e comunicar em até 3 dias úteis
  (Res. CD/ANPD nº 15/2024).
- **Procurações:** controle de vigência e revogação, com alertas de vencimento.
