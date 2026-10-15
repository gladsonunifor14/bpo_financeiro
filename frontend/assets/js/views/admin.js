import { api, sessao } from '../api.js';
import {
  h, botao, botaoIcone, campo, carregando, cnpj, comCarregamento, confirmar, dadosFormulario, dataHora, dialogo,
  erroCarga, mostrarErros, notificar, paginacao, selo, tabela, vazio,
} from '../ui.js';

// ------------------------------------------------------------------ termos LGPD
export async function termos(alvo) {
  const lista = await api('/termos');
  alvo.append(h('h1', {}, 'Termos, privacidade e confidencialidade'),
    h('p', {}, 'Leia cada documento. O aceite fica registrado com data, hora, IP e o código de integridade (hash) do texto.'));
  const pendentes = lista.filter((t) => t.obrigatorio && !t.aceito_em);
  if (pendentes.length) alvo.append(h('div', { class: 'aviso aviso-alerta', role: 'status' }, h('p', {}, `Você tem ${pendentes.length} documento(s) para aceitar antes de continuar.`)));
  for (const t of lista) {
    const sec = h('section', { class: 'cartao', 'aria-labelledby': `termo-${t.id}-titulo` },
      h('h2', { id: `termo-${t.id}-titulo` }, `${t.titulo} (versão ${t.versao}) `, t.aceito_em ? selo(`Aceito em ${dataHora(t.aceito_em)}`, 'sucesso') : selo('Aceite pendente', 'alerta')),
      h('div', { class: 'texto-contrato', tabindex: '0', role: 'document', 'aria-label': t.titulo }, t.conteudo));
    if (!t.aceito_em) {
      const form = h('form', { id: `form-termo-${t.id}`, novalidate: true },
        campo({ id: `aceite-termo-${t.id}`, nome: 'aceite', tipo: 'checkbox', obrigatorio: true, rotulo: `Li e aceito: ${t.titulo}` }),
        botao(`Registrar aceite de “${t.titulo}”`, { id: `botao-aceitar-termo-${t.id}`, tipo: 'submit', icone: 'check' }));
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!form.elements.aceite.checked) { mostrarErros(form, { message: 'Marque a caixa para confirmar a leitura.', campos: { aceite: 'Confirme que leu o documento' } }); return; }
        await comCarregamento(form.querySelector('[type=submit]'), async () => {
          await api(`/termos/${t.id}/aceite`, { metodo: 'POST', corpo: { hash_sha256: t.hash_sha256 } });
          notificar('Aceite registrado.');
          const restantes = (await api('/termos/pendentes')).length;
          if (!restantes) location.hash = '#/'; else { alvo.replaceChildren(); termos(alvo); }
        });
      });
      sec.append(form);
    }
    alvo.append(sec);
  }
  if (sessao.usuario.papel === 'admin') alvo.append(formNovoTermo(alvo));
}

function formNovoTermo(alvo) {
  const form = h('form', { id: 'form-novo-termo', novalidate: true },
    campo({ id: 'termo-tipo', nome: 'tipo', rotulo: 'Documento', tipo: 'select', opcoes: [
      { valor: 'termos_uso', rotulo: 'Termos de Uso' }, { valor: 'politica_privacidade', rotulo: 'Política de Privacidade' },
      { valor: 'confidencialidade', rotulo: 'Termo de Confidencialidade' }, { valor: 'tratamento_dados', rotulo: 'Acordo de tratamento de dados' }] }),
    campo({ id: 'termo-titulo', nome: 'titulo', rotulo: 'Título', obrigatorio: true }),
    campo({ id: 'termo-conteudo', nome: 'conteudo', rotulo: 'Texto integral', tipo: 'textarea', obrigatorio: true }),
    botao('Publicar nova versão', { id: 'botao-publicar-termo', tipo: 'submit' }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!(await confirmar('Publicar nova versão? Todos os usuários precisarão aceitar novamente.'))) return;
    try {
      await api('/termos', { metodo: 'POST', corpo: dadosFormulario(form) });
      notificar('Nova versão publicada.');
      alvo.replaceChildren(); termos(alvo);
    } catch (erro) { mostrarErros(form, erro); }
  });
  return h('details', { class: 'cartao' }, h('summary', { id: 'abrir-novo-termo' }, 'Publicar nova versão de documento (administrador)'), form);
}

// ------------------------------------------------------------------ escritório
export async function escritorio(alvo) {
  const esc = await api('/escritorio');
  const admin = sessao.usuario.papel === 'admin';
  const form = h('form', { id: 'form-escritorio', novalidate: true },
    h('div', { class: 'grade-2' },
      campo({ id: 'esc-razao', nome: 'razao_social', rotulo: 'Razão social', valor: esc.razao_social, atributos: { readonly: !admin } }),
      campo({ id: 'esc-fantasia', nome: 'nome_fantasia', rotulo: 'Nome fantasia', valor: esc.nome_fantasia, atributos: { readonly: !admin } }),
      campo({ id: 'esc-crc', nome: 'crc', rotulo: 'CRC', valor: esc.crc, dica: 'Aparece em todos os relatórios', atributos: { readonly: !admin } }),
      campo({ id: 'esc-responsavel', nome: 'responsavel_tecnico', rotulo: 'Responsável técnico', valor: esc.responsavel_tecnico, atributos: { readonly: !admin } }),
      campo({ id: 'esc-email', nome: 'email', rotulo: 'E-mail', tipo: 'email', valor: esc.email, atributos: { readonly: !admin } }),
      campo({ id: 'esc-telefone', nome: 'telefone', rotulo: 'Telefone', valor: esc.telefone, atributos: { readonly: !admin } })),
    admin ? h('div', { class: 'acoes' }, botao('Salvar', { id: 'botao-salvar-escritorio', tipo: 'submit' }),
      botao('Atualizar com dados da Receita', { id: 'botao-receita-escritorio', variante: 'botao-secundario', icone: 'busca', aoClicar: async (e) => comCarregamento(e.currentTarget, async () => {
        try { await api('/escritorio/reimportar-receita', { metodo: 'POST' }); notificar('Dados atualizados.'); alvo.replaceChildren(); escritorio(alvo); } catch (er) { notificar(er.message, 'erro'); }
      }) })) : h('p', { class: 'texto-suave' }, 'Somente administradores podem alterar estes dados.'));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try { await api('/escritorio', { metodo: 'PUT', corpo: dadosFormulario(form) }); notificar('Dados do escritório salvos.'); } catch (erro) { mostrarErros(form, erro); }
    });
  });
  alvo.append(h('h1', {}, 'Escritório'),
    h('p', { class: 'texto-suave' }, `CNPJ ${cnpj(esc.cnpj)} · ${esc.situacao_cadastral || 'situação não informada'} · ${[esc.logradouro, esc.numero, esc.bairro, esc.municipio && `${esc.municipio}/${esc.uf}`].filter(Boolean).join(', ')}`),
    h('section', { class: 'cartao', 'aria-labelledby': 'titulo-dados-esc' }, h('h2', { id: 'titulo-dados-esc' }, 'Identificação nos relatórios'), form));

  const modelos = await api('/modelos-contrato');
  const ativo = modelos.find((m) => m.ativo);
  const formModelo = h('form', { id: 'form-modelo-contrato', novalidate: true },
    campo({ id: 'modelo-titulo', nome: 'titulo', rotulo: 'Título', valor: ativo?.titulo, obrigatorio: true }),
    campo({ id: 'modelo-conteudo', nome: 'conteudo', rotulo: 'Texto do contrato de adesão', tipo: 'textarea', valor: ativo?.conteudo, obrigatorio: true,
      dica: 'Variáveis: {{cliente_razao_social}}, {{cliente_cnpj}}, {{valor_mensal}}, {{dia_vencimento}}, {{inicio_vigencia}}, {{prazo}}, {{escritorio_razao_social}}, {{escritorio_cnpj}}, {{escritorio_crc}}…',
      atributos: { rows: '16', readonly: !admin } }),
    admin ? botao('Publicar nova versão do modelo', { id: 'botao-publicar-modelo', tipo: 'submit' }) : null);
  formModelo.addEventListener('submit', async (e) => {
    e.preventDefault();
    try { const m = await api('/modelos-contrato', { metodo: 'POST', corpo: dadosFormulario(formModelo) }); notificar(`Modelo versão ${m.versao} publicado. Contratos já emitidos não mudam.`); } catch (erro) { mostrarErros(formModelo, erro); }
  });
  alvo.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-modelo' }, h('h2', { id: 'titulo-modelo' }, `Modelo de contrato (versão ${ativo?.versao || 1})`), formModelo));

  const plano = await api('/plano-contas');
  const GRUPOS = ['receita_bruta', 'deducoes', 'custos', 'despesas_operacionais', 'receitas_financeiras', 'despesas_financeiras', 'outras_receitas', 'outras_despesas', 'impostos_lucro', 'nao_dre'];
  const formConta = h('form', { id: 'form-nova-conta', class: 'linha', novalidate: true },
    campo({ id: 'nova-conta-codigo', nome: 'codigo', rotulo: 'Código', obrigatorio: true, dica: 'Ex.: 4.2.11' }),
    campo({ id: 'nova-conta-nome', nome: 'nome', rotulo: 'Nome', obrigatorio: true }),
    campo({ id: 'nova-conta-grupo', nome: 'grupo', rotulo: 'Grupo na DRE', tipo: 'select', opcoes: GRUPOS.map((g) => ({ valor: g, rotulo: g === 'nao_dre' ? 'Fora da DRE (patrimonial)' : g.replace(/_/g, ' ') })) }),
    h('div', { class: 'campo' }, botao('Adicionar conta', { id: 'botao-adicionar-conta', tipo: 'submit', icone: 'mais' })));
  formConta.addEventListener('submit', async (e) => {
    e.preventDefault();
    try { await api('/plano-contas', { metodo: 'POST', corpo: dadosFormulario(formConta) }); notificar('Conta adicionada.'); alvo.replaceChildren(); escritorio(alvo); } catch (erro) { mostrarErros(formConta, erro); }
  });
  alvo.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-plano' }, h('h2', { id: 'titulo-plano' }, 'Plano de contas gerencial'),
    formConta,
    tabela({ id: 'tabela-plano', legenda: `Contas (${plano.length})`, linhas: plano,
      colunas: [{ titulo: 'Código', valor: (c) => c.codigo }, { titulo: 'Nome', valor: (c) => c.nome }, { titulo: 'Grupo', valor: (c) => c.grupo.replace(/_/g, ' ') }] })));
}

// ------------------------------------------------------------------ usuários
export async function usuarios(alvo) {
  const [lista, clientes] = await Promise.all([api('/usuarios'), api('/clientes?por_pagina=100')]);
  const form = h('form', { id: 'form-usuario', novalidate: true },
    h('div', { class: 'grade-2' },
      campo({ id: 'usuario-nome', nome: 'nome', rotulo: 'Nome', obrigatorio: true }),
      campo({ id: 'usuario-email', nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true }),
      campo({ id: 'usuario-papel', nome: 'papel', rotulo: 'Perfil', tipo: 'select', opcoes: [
        { valor: 'analista', rotulo: 'Analista do escritório' }, { valor: 'admin', rotulo: 'Administrador' }, { valor: 'cliente', rotulo: 'Cliente (acesso à própria empresa)' }] }),
      campo({ id: 'usuario-cliente', nome: 'cliente_id', rotulo: 'Empresa do cliente', tipo: 'select', dica: 'Obrigatório para o perfil cliente',
        opcoes: [{ valor: '', rotulo: clientes.total ? 'Selecione…' : 'Nenhum cliente cadastrado' }, ...clientes.itens.map((c) => ({ valor: c.id, rotulo: c.razao_social }))] }),
      campo({ id: 'usuario-senha', nome: 'senha_inicial', rotulo: 'Senha inicial', tipo: 'password', obrigatorio: true, autocomplete: 'new-password',
        dica: 'Informe ao usuário por canal seguro; ele poderá alterá-la em Minha conta. O login sempre exige o código enviado por e-mail.' })),
    botao('Criar usuário', { id: 'botao-criar-usuario', tipo: 'submit', icone: 'mais' }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = dadosFormulario(form);
    if (d.cliente_id) d.cliente_id = Number(d.cliente_id);
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try { await api('/usuarios', { metodo: 'POST', corpo: d }); notificar('Usuário criado.'); alvo.replaceChildren(); usuarios(alvo); } catch (erro) { mostrarErros(form, erro); }
    });
  });
  alvo.append(h('h1', {}, 'Usuários'),
    tabela({ id: 'tabela-usuarios', legenda: 'Usuários com acesso', linhas: lista,
      colunas: [
        { titulo: 'Nome', valor: (u) => u.nome }, { titulo: 'E-mail', valor: (u) => u.email },
        { titulo: 'Perfil', valor: (u) => u.papel },
        { titulo: 'Situação', valor: (u) => (u.ativo ? selo('Ativo', 'sucesso') : selo('Desativado', 'neutro')) },
        { titulo: 'Último acesso', valor: (u) => dataHora(u.ultimo_login_em) },
      ],
      acoes: (u) => (u.id === sessao.usuario.id ? [] : [botao(u.ativo ? 'Desativar' : 'Reativar', {
        id: `alternar-usuario-${u.id}`, variante: u.ativo ? 'botao-perigo' : 'botao-secundario', rotulo: `${u.ativo ? 'Desativar' : 'Reativar'} o usuário ${u.nome}`,
        aoClicar: async () => {
          if (u.ativo && !(await confirmar(`Desativar o acesso de ${u.nome}?`, { perigo: true, textoConfirmar: 'Desativar' }))) return;
          await api(`/usuarios/${u.id}`, { metodo: 'PATCH', corpo: { ativo: !u.ativo } });
          notificar('Usuário atualizado.');
          alvo.replaceChildren(); usuarios(alvo);
        },
      })]) }),
    h('section', { class: 'cartao', 'aria-labelledby': 'titulo-novo-usuario' }, h('h2', { id: 'titulo-novo-usuario' }, 'Novo usuário'), form));
}

// ------------------------------------------------------------------ integrações
export async function integracoes(alvo) {
  const chaves = await api('/chaves-api');
  const form = h('form', { id: 'form-chave', class: 'linha', novalidate: true },
    campo({ id: 'chave-nome', nome: 'nome', rotulo: 'Nome da integração', obrigatorio: true, dica: 'Ex.: ERP do cliente, Power BI' }),
    h('div', { class: 'campo' }, botao('Gerar chave de API', { id: 'botao-gerar-chave', tipo: 'submit', icone: 'mais' })));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const c = await api('/chaves-api', { metodo: 'POST', corpo: dadosFormulario(form) });
      let d;
      const campoChave = h('input', { id: 'chave-gerada', readonly: true, value: c.chave, 'aria-describedby': 'chave-gerada-aviso' });
      d = dialogo({ titulo: 'Chave gerada', conteudo: h('div', {},
        h('label', { for: 'chave-gerada' }, 'Chave de API'), campoChave,
        h('p', { id: 'chave-gerada-aviso', class: 'aviso aviso-alerta' }, 'Copie agora: por segurança, a chave não será exibida novamente. Envie-a no cabeçalho X-API-Key.')),
      acoes: [botao('Copiar chave', { id: 'copiar-chave', aoClicar: async () => { await navigator.clipboard?.writeText(c.chave); notificar('Chave copiada.'); } }),
        botao('Fechar', { id: 'fechar-chave', variante: 'botao-secundario', aoClicar: () => { d.close(); alvo.replaceChildren(); integracoes(alvo); } })] });
      campoChave.select();
    } catch (erro) { mostrarErros(form, erro); }
  });
  alvo.append(h('h1', {}, 'Integrações (API)'),
    h('p', {}, 'Sistemas externos podem consultar dados e enviar documentos pela API REST. ', h('a', { href: '/api/docs', id: 'link-swagger', target: '_blank', rel: 'noopener' }, 'Abrir documentação Swagger', h('span', { class: 'sr-only' }, ' (abre em nova aba)'))),
    h('section', { class: 'cartao', 'aria-labelledby': 'titulo-nova-chave' }, h('h2', { id: 'titulo-nova-chave' }, 'Nova chave'), form),
    chaves.length ? tabela({ id: 'tabela-chaves', legenda: 'Chaves de API', linhas: chaves,
      colunas: [
        { titulo: 'Nome', valor: (c) => c.nome }, { titulo: 'Prefixo', valor: (c) => `${c.prefixo}…` },
        { titulo: 'Criada em', valor: (c) => dataHora(c.criado_em) }, { titulo: 'Último uso', valor: (c) => dataHora(c.ultimo_uso_em) },
        { titulo: 'Situação', valor: (c) => (c.revogada_em ? selo('Revogada', 'neutro') : selo('Ativa', 'sucesso')) },
      ],
      acoes: (c) => (c.revogada_em ? [] : [botaoIcone('revogar', `Revogar a chave ${c.nome}`, async () => {
        if (!(await confirmar(`Revogar a chave “${c.nome}”? Integrações que a usam deixarão de funcionar.`, { perigo: true, textoConfirmar: 'Revogar' }))) return;
        await api(`/chaves-api/${c.id}`, { metodo: 'DELETE' });
        alvo.replaceChildren(); integracoes(alvo);
      }, { id: `revogar-chave-${c.id}`, perigo: true })]) })
      : vazio({ titulo: 'Nenhuma chave criada', texto: 'Crie uma chave para integrar ERPs ou ferramentas de BI externas.' }));
}

// ------------------------------------------------------------------ auditoria
export async function auditoria(alvo) {
  let pagina = 1;
  const resultado = h('div', { 'aria-live': 'polite' });
  const form = h('form', { id: 'form-auditoria', class: 'linha', role: 'search' },
    campo({ id: 'aud-tabela', nome: 'tabela', rotulo: 'Tabela', tipo: 'select', opcoes: [{ valor: '', rotulo: 'Todas' },
      ...['cliente', 'usuario', 'escritorio', 'contrato', 'nota_fiscal', 'item_nota', 'lancamento_bancario', 'posicao_aplicacao', 'procuracao', 'termo_versao', 'chave_api'].map((t) => ({ valor: t, rotulo: t }))] }),
    campo({ id: 'aud-acao', nome: 'acao', rotulo: 'Ação', tipo: 'select', opcoes: [{ valor: '', rotulo: 'Todas' }, ...['INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'LOGIN_FALHA', 'SENHA_ALTERADA', 'ACEITE_CONTRATO', 'EXPORTACAO_LGPD'].map((a) => ({ valor: a, rotulo: a }))] }),
    campo({ id: 'aud-inicio', nome: 'inicio', rotulo: 'De', tipo: 'date' }),
    campo({ id: 'aud-fim', nome: 'fim', rotulo: 'Até', tipo: 'date' }),
    h('div', { class: 'campo' }, botao('Filtrar', { id: 'botao-filtrar-auditoria', tipo: 'submit', variante: 'botao-secundario' })));
  form.addEventListener('submit', (e) => { e.preventDefault(); pagina = 1; carregar(); });
  alvo.append(h('h1', {}, 'Trilha de auditoria'), h('p', { class: 'texto-suave' }, 'Registro imutável de quem alterou o quê e quando, com valores antes e depois.'), form, resultado);

  async function carregar() {
    carregando(resultado);
    try {
      const q = new URLSearchParams({ ...dadosFormulario(form), pagina, por_pagina: 50 });
      const r = await api(`/auditoria?${q}`);
      if (!r.total) { resultado.replaceChildren(vazio({ titulo: 'Nenhum registro encontrado' })); return; }
      const resumo = (a) => {
        if (a.campos_alterados?.length) return a.campos_alterados.map((c) => `${c}: ${fmt(a.dados_antes?.[c])} → ${fmt(a.dados_depois?.[c])}`).join('; ');
        return '';
      };
      resultado.replaceChildren(tabela({ id: 'tabela-auditoria', legenda: `Eventos (${r.total})`, linhas: r.itens,
        tituloCartao: (a) => `${a.acao} ${a.tabela || ''} #${a.registro_id || ''}`,
        colunas: [
          { titulo: 'Quando', valor: (a) => dataHora(a.criado_em) },
          { titulo: 'Quem', valor: (a) => a.usuario_email || 'sistema' },
          { titulo: 'Ação', valor: (a) => a.acao },
          { titulo: 'Registro', valor: (a) => `${a.tabela || '—'} ${a.registro_id ? `#${a.registro_id}` : ''}` },
          { titulo: 'Alterações', valor: (a) => resumo(a) || '—' },
          { titulo: 'IP', valor: (a) => a.ip || '—' },
        ] }), paginacao({ id: 'auditoria', pagina, porPagina: 50, total: r.total, aoMudar: (p) => { pagina = p; carregar(); } }));
    } catch (e) { erroCarga(resultado, e, carregar); }
  }
  carregar();
}

function fmt(v) {
  if (v === null || v === undefined) return '∅';
  return typeof v === 'object' ? JSON.stringify(v) : String(v);
}
