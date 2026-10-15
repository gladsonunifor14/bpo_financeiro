import { api, baixar } from '../api.js';
import {
  h, botao, botaoIcone, campo, carregando, cnpj, comCarregamento, confirmar, dadosFormulario, data, dialogo, erroCarga,
  moeda, mostrarErros, notificar, paginacao, pct, prerequisito, selo, tabela, vazio, anunciar,
} from '../ui.js';

const opcoesPlano = (plano, rotuloVazio = 'Selecione a conta…') => [
  { valor: '', rotulo: rotuloVazio },
  ...plano.filter((c) => c.ativo).map((c) => ({ valor: c.id, rotulo: `${c.codigo} — ${c.nome}` })),
];
const nomeConta = (plano, id) => { const c = plano.find((x) => x.id === id); return c ? `${c.codigo} — ${c.nome}` : 'Não classificada'; };

// ================================================================== notas fiscais
export function abaNotas(painel, ctx) {
  const { id, plano, equipe } = ctx;
  const resultadoImport = h('div', { id: 'resultado-importacao-notas', 'aria-live': 'polite' });
  const lista = h('div', { id: 'lista-notas' });
  let filtros = { tipo: '', pagina: 1, pendentes: false };

  const form = h('form', { id: 'form-importar-notas', novalidate: true },
    campo({ id: 'notas-arquivos', nome: 'arquivos', rotulo: 'Arquivos XML de NF-e ou ZIP', tipo: 'file', obrigatorio: true,
      dica: 'Selecione um ou mais XML (emitidas ou recebidas) ou um ZIP com até 500 notas. O sistema identifica o tipo e classifica pelo CFOP.',
      atributos: { accept: '.xml,.zip,application/xml,text/xml,application/zip', multiple: true } }),
    h('div', { class: 'acoes acoes-fixas' }, botao('Importar notas', { id: 'botao-importar-notas', tipo: 'submit', icone: 'enviar' })));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const arquivos = form.elements.arquivos.files;
    if (!arquivos.length) { mostrarErros(form, { message: 'Selecione ao menos um arquivo.', campos: { arquivos: 'Selecione os arquivos XML ou ZIP' } }); return; }
    const fd = new FormData();
    for (const f of arquivos) fd.append('arquivos', f);
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        const res = await api(`/clientes/${id}/notas/importar`, { metodo: 'POST', formulario: fd });
        const cont = res.reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {});
        const msg = `Importação concluída: ${cont.importada || 0} importada(s), ${cont.duplicada || 0} duplicada(s), ${cont.erro || 0} com erro, ${cont.ignorada || 0} ignorada(s).`;
        const tipos = { importada: 'sucesso', duplicada: 'info', erro: 'erro', ignorada: 'alerta' };
        resultadoImport.replaceChildren(h('div', { class: `aviso ${cont.erro ? 'aviso-alerta' : 'aviso-sucesso'}`, role: 'status' }, h('p', {}, msg),
          h('ul', {}, res.map((r) => h('li', {}, selo(r.status, tipos[r.status]), ` ${r.arquivo}: ${r.mensagem}`)))));
        anunciar(msg);
        form.reset();
        carregar();
      } catch (erro) { mostrarErros(form, erro); }
    });
  });

  const filtro = h('form', { id: 'form-filtro-notas', class: 'linha', role: 'search' },
    campo({ id: 'filtro-notas-tipo', nome: 'tipo', rotulo: 'Tipo', tipo: 'select', opcoes: [{ valor: '', rotulo: 'Todas' }, { valor: 'emitida', rotulo: 'Emitidas (saídas)' }, { valor: 'recebida', rotulo: 'Recebidas (entradas)' }] }),
    campo({ id: 'filtro-notas-pendentes', nome: 'pendentes', tipo: 'checkbox', rotulo: 'Somente com itens sem classificação' }),
    h('div', { class: 'campo' }, botao('Filtrar', { id: 'botao-filtrar-notas', tipo: 'submit', variante: 'botao-secundario' })));
  filtro.addEventListener('submit', (e) => { e.preventDefault(); const d = dadosFormulario(filtro); filtros = { tipo: d.tipo || '', pendentes: d.pendentes, pagina: 1 }; carregar(); });

  painel.append(h('h2', {}, 'Notas fiscais'),
    h('section', { class: 'cartao', 'aria-labelledby': 'titulo-importar-notas' }, h('h3', { id: 'titulo-importar-notas' }, 'Importar XML'), form, resultadoImport),
    h('section', { 'aria-labelledby': 'titulo-lista-notas' }, h('h3', { id: 'titulo-lista-notas' }, 'Notas importadas'), filtro, lista));

  async function carregar() {
    carregando(lista);
    try {
      const q = new URLSearchParams({ pagina: filtros.pagina, por_pagina: 20 });
      if (filtros.tipo) q.set('tipo', filtros.tipo);
      if (filtros.pendentes) q.set('pendentes', 'true');
      const r = await api(`/clientes/${id}/notas?${q}`);
      if (!r.total) {
        lista.replaceChildren(vazio({ titulo: 'Nenhuma nota encontrada', nivel: 'h4', texto: 'Importe os XML das notas emitidas e recebidas para alimentar a DRE e o fluxo de caixa projetado.',
          ctas: [botao('Selecionar arquivos XML', { id: 'cta-selecionar-xml', icone: 'enviar', aoClicar: () => form.elements.arquivos.focus() })] }));
        return;
      }
      lista.replaceChildren(tabela({
        id: 'tabela-notas', legenda: `Notas fiscais (${r.total})`, linhas: r.itens,
        tituloCartao: (n) => `NF-e ${n.numero} — ${n.tipo === 'emitida' ? n.destinatario_nome || 'Consumidor' : n.emitente_nome}`,
        colunas: [
          { titulo: 'Número', valor: (n) => `${n.numero}/${n.serie || '-'}` },
          { titulo: 'Emissão', valor: (n) => data(n.data_emissao) },
          { titulo: 'Tipo', valor: (n) => (n.tipo === 'emitida' ? selo('Emitida', 'info') : selo('Recebida', 'neutro')) },
          { titulo: 'Contraparte', valor: (n) => (n.tipo === 'emitida' ? `${n.destinatario_nome || '—'} (${cnpj(n.destinatario_documento)})` : `${n.emitente_nome} (${cnpj(n.emitente_documento)})`) },
          { titulo: 'Natureza', valor: (n) => n.natureza_operacao || '—' },
          { titulo: 'Valor total', num: true, valor: (n) => moeda(n.valor_total) },
        ],
        acoes: (n) => [
          botaoIcone('olho', `Ver itens e classificação da nota ${n.numero}`, () => verNota(n.id, plano, carregar), { id: `ver-nota-${n.id}` }),
          botaoIcone('baixar', `Baixar XML da nota ${n.numero}`, () => baixar(`/notas/${n.id}/xml`, `${n.chave}.xml`), { id: `xml-nota-${n.id}` }),
          equipe ? botaoIcone('lixeira', `Excluir nota ${n.numero} de ${n.tipo === 'emitida' ? n.destinatario_nome : n.emitente_nome}`, async () => {
            if (!(await confirmar(`Excluir a nota ${n.numero}? Ela deixará de compor os relatórios.`, { perigo: true, textoConfirmar: 'Excluir nota' }))) return;
            await api(`/notas/${n.id}`, { metodo: 'DELETE' });
            notificar(`Nota ${n.numero} excluída.`);
            carregar();
          }, { id: `excluir-nota-${n.id}`, perigo: true }) : null,
        ].filter(Boolean),
      }), paginacao({ id: 'notas', pagina: filtros.pagina, porPagina: 20, total: r.total, aoMudar: (p) => { filtros.pagina = p; carregar(); } }));
    } catch (e) { erroCarga(lista, e, carregar); }
  }
  carregar();
}

async function verNota(notaId, plano, aoAlterar) {
  const n = await api(`/notas/${notaId}`);
  const corpo = h('div', {},
    h('p', {}, `Chave: ${n.chave}`),
    h('p', {}, `${n.tipo === 'emitida' ? 'Emitida' : 'Recebida'} em ${data(n.data_emissao)} · Total ${moeda(n.valor_total)} · ICMS ${moeda(n.valor_icms)} · PIS ${moeda(n.valor_pis)} · COFINS ${moeda(n.valor_cofins)}`),
    tabela({
      id: `tabela-itens-${n.id}`, legenda: 'Itens e classificação contábil', linhas: n.itens,
      tituloCartao: (i) => `Item ${i.numero_item}: ${i.descricao}`,
      colunas: [
        { titulo: 'Item', valor: (i) => `${i.numero_item}. ${i.descricao}` },
        { titulo: 'CFOP', valor: (i) => i.cfop },
        { titulo: 'Valor', num: true, valor: (i) => moeda(i.valor_total) },
        { titulo: 'Origem', valor: (i) => ({ cfop: selo('Automática (CFOP)', 'info'), manual: selo('Manual', 'sucesso'), pendente: selo('Pendente', 'alerta') }[i.classificacao_origem]) },
        { titulo: 'Conta contábil', valor: (i) => {
          const sel = campo({ id: `item-conta-${i.id}`, nome: 'conta_id', rotulo: `Conta do item ${i.numero_item}`, tipo: 'select', valor: i.conta_id, opcoes: opcoesPlano(plano) });
          sel.querySelector('select').addEventListener('change', async (e) => {
            if (!e.target.value) return;
            try {
              await api(`/notas/itens/${i.id}/classificacao`, { metodo: 'PUT', corpo: { conta_id: Number(e.target.value) } });
              anunciar(`Item ${i.numero_item} classificado em ${nomeConta(plano, Number(e.target.value))}.`);
              aoAlterar();
            } catch (er) { notificar(er.message, 'erro'); }
          });
          return sel;
        } },
      ],
    }),
    n.duplicatas.length ? h('p', {}, `Duplicatas: ${n.duplicatas.map((d) => `${d.numero || ''} ${data(d.vencimento)} ${moeda(d.valor)}`).join('; ')}`) : null);
  let d;
  d = dialogo({ titulo: `NF-e ${n.numero} — ${n.tipo === 'emitida' ? n.destinatario_nome || '' : n.emitente_nome}`, conteudo: corpo,
    acoes: [botao('Fechar', { id: 'fechar-nota', aoClicar: () => d.close() })] });
}

// ================================================================== extratos
export async function abaExtratos(painel, ctx) {
  const { id, plano } = ctx;
  carregando(painel);
  let contas;
  let of;
  try { [contas, of] = await Promise.all([api(`/clientes/${id}/contas-bancarias`), api('/open-finance/status')]); } catch (e) { erroCarga(painel, e); return; }
  const correntes = contas.filter((c) => c.tipo === 'corrente');
  painel.replaceChildren(h('h2', {}, 'Extratos bancários'));

  // --- contas bancárias
  const formConta = formularioConta(id, 'corrente', () => abaExtratos(painel, ctx));
  painel.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-contas' }, h('h3', { id: 'titulo-contas' }, 'Contas correntes'),
    correntes.length
      ? h('ul', {}, correntes.map((c) => h('li', {}, `${c.banco_nome} — ag. ${c.agencia || '—'} c/c ${c.numero_conta || '—'}${c.descricao ? ` (${c.descricao})` : ''}`)))
      : h('p', {}, 'Nenhuma conta corrente cadastrada.'),
    h('details', { open: !correntes.length }, h('summary', { id: 'abrir-form-conta' }, 'Cadastrar conta corrente'), formConta)));

  // --- importação
  const semConta = !correntes.length;
  const idPre = 'pre-import-extrato';
  const resultado = h('div', { 'aria-live': 'polite' });
  const formImp = h('form', { id: 'form-importar-extrato', novalidate: true },
    h('div', { class: 'grade-2' },
      campo({ id: 'extrato-conta', nome: 'conta', rotulo: 'Conta bancária', tipo: 'select', obrigatorio: true, atributos: { disabled: semConta },
        opcoes: semConta ? [{ valor: '', rotulo: 'Cadastre uma conta primeiro' }] : correntes.map((c) => ({ valor: c.id, rotulo: `${c.banco_nome} ${c.numero_conta || ''}` })) }),
      campo({ id: 'extrato-arquivo', nome: 'arquivo', rotulo: 'Arquivo OFX ou CSV', tipo: 'file', obrigatorio: true, atributos: { accept: '.ofx,.csv,.txt', disabled: semConta },
        dica: 'CSV: colunas data; historico; valor (ou debito e credito). Lançamentos repetidos são ignorados.' })),
    h('div', { class: 'acoes acoes-fixas' }, botao('Importar extrato', { id: 'botao-importar-extrato', tipo: 'submit', icone: 'enviar', desabilitado: semConta, descritoPor: semConta ? idPre : undefined })),
    semConta ? prerequisito(idPre, 'Para importar extratos, cadastre antes a conta corrente.', botao('Cadastrar conta corrente', { id: 'cta-cadastrar-conta', variante: 'botao-secundario', aoClicar: () => { const s = document.getElementById('abrir-form-conta'); s.parentElement.open = true; document.getElementById('conta-banco-nome-corrente').focus(); } })) : null,
    resultado);
  formImp.addEventListener('submit', async (e) => {
    e.preventDefault();
    const arq = formImp.elements.arquivo.files[0];
    if (!arq) { mostrarErros(formImp, { message: 'Selecione o arquivo.', campos: { arquivo: 'Selecione o arquivo OFX ou CSV' } }); return; }
    const fd = new FormData();
    fd.append('arquivo', arq);
    await comCarregamento(formImp.querySelector('[type=submit]'), async () => {
      try {
        const r = await api(`/contas-bancarias/${formImp.elements.conta.value}/extratos`, { metodo: 'POST', formulario: fd });
        const msg = `${r.quantidade} lançamento(s) importado(s), ${r.duplicados} já existente(s). A IA classificou ${r.classificados_ia} automaticamente para sua revisão.`;
        resultado.replaceChildren(h('div', { class: 'aviso aviso-sucesso', role: 'status' }, h('p', {}, msg)));
        anunciar(msg);
        formImp.reset();
        carregarLancamentos();
      } catch (erro) { mostrarErros(formImp, erro); }
    });
  });
  painel.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-importar-extrato' }, h('h3', { id: 'titulo-importar-extrato' }, 'Importar extrato'), formImp));

  // --- open finance
  const idPreOf = 'pre-open-finance';
  painel.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-open-finance' }, h('h3', { id: 'titulo-open-finance' }, 'Open Finance'),
    of.disponivel
      ? h('p', {}, `Integração ativa via ${of.provedor}. O cliente autoriza o compartilhamento no app do banco.`)
      : prerequisito(idPreOf, of.motivo),
    botao('Conectar banco via Open Finance', {
      id: 'botao-open-finance', variante: 'botao-secundario', desabilitado: !of.disponivel || semConta, descritoPor: !of.disponivel ? idPreOf : undefined,
      aoClicar: async (e) => comCarregamento(e.currentTarget, async () => {
        try {
          const c = await api('/open-finance/consentimentos', { metodo: 'POST', corpo: { cliente_id: id } });
          const hoje = new Date();
          const inicio = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1).toISOString().slice(0, 10);
          const r = await api(`/open-finance/consentimentos/${c.id}/sincronizar`, { metodo: 'POST', corpo: { conta_bancaria_id: correntes[0].id, inicio, fim: hoje.toISOString().slice(0, 10) } });
          notificar(`${r.quantidade} transações importadas via Open Finance.`);
          carregarLancamentos();
        } catch (er) { notificar(er.message, 'erro'); }
      }),
    })));

  // --- lançamentos e classificação
  const lista = h('div', { id: 'lista-lancamentos' });
  let filtros = { status: 'pendente', pagina: 1 };
  const filtro = h('form', { id: 'form-filtro-lancamentos', class: 'linha', role: 'search' },
    campo({ id: 'filtro-status', nome: 'status', rotulo: 'Situação da classificação', tipo: 'select', valor: 'pendente', opcoes: [
      { valor: '', rotulo: 'Todas' }, { valor: 'pendente', rotulo: 'Pendentes' }, { valor: 'ia_sugerida', rotulo: 'Sugeridas pela IA (revisar)' },
      { valor: 'manual', rotulo: 'Classificadas manualmente' }, { valor: 'ia_confirmada', rotulo: 'IA confirmada' }] }),
    h('div', { class: 'campo' }, botao('Filtrar', { id: 'botao-filtrar-lancamentos', tipo: 'submit', variante: 'botao-secundario' })));
  filtro.addEventListener('submit', (e) => { e.preventDefault(); filtros = { status: dadosFormulario(filtro).status || '', pagina: 1 }; carregarLancamentos(); });
  const botaoIA = botao('Classificar pendentes com IA', { id: 'botao-rodar-ia', icone: 'ia', variante: 'botao-secundario', aoClicar: (e) => comCarregamento(e.currentTarget, async () => {
    const r = await api(`/clientes/${id}/lancamentos/classificar-ia`, { metodo: 'POST' });
    const aplicadas = r.filter((s) => s.aplicada).length;
    notificar(aplicadas ? `A IA classificou ${aplicadas} lançamento(s). Revise e confirme.` : 'A IA ainda não tem confiança suficiente. Classifique alguns lançamentos manualmente para ensiná-la.', aplicadas ? 'sucesso' : 'info');
    carregarLancamentos();
  }) });
  painel.append(h('section', { 'aria-labelledby': 'titulo-lancamentos' }, h('h3', { id: 'titulo-lancamentos' }, 'Classificação dos lançamentos'),
    h('div', { class: 'aviso aviso-info' }, h('p', {}, 'Classifique cada lançamento pela conta adequada. Ao classificar, os lançamentos com o mesmo histórico e natureza são replicados automaticamente; nos próximos extratos, a IA aplica o que aprendeu. Recebimentos de clientes e pagamentos de fornecedores com nota devem ir para as contas 9.1.01/9.1.02 para não duplicar valores na DRE.')),
    filtro, h('div', { class: 'acoes' }, botaoIA), lista));

  async function carregarLancamentos() {
    carregando(lista);
    try {
      const q = new URLSearchParams({ pagina: filtros.pagina, por_pagina: 50 });
      if (filtros.status) q.set('status_classificacao', filtros.status);
      const r = await api(`/clientes/${id}/lancamentos?${q}`);
      if (!r.total) {
        lista.replaceChildren(vazio({ nivel: 'h4', titulo: filtros.status === 'pendente' ? 'Nenhum lançamento pendente' : 'Nenhum lançamento encontrado',
          texto: semConta ? 'Cadastre a conta corrente e importe o primeiro extrato.' : 'Importe um extrato OFX ou CSV para começar.',
          ctas: [botao('Importar extrato', { id: 'cta-importar-extrato', icone: 'enviar', desabilitado: semConta, aoClicar: () => formImp.elements.arquivo.focus() })] }));
        return;
      }
      const sugeridas = r.itens.filter((l) => l.status_classificacao === 'ia_sugerida');
      const confirmarTodas = botao(`Confirmar ${sugeridas.length} sugestão(ões) da IA nesta página`, {
        id: 'botao-confirmar-sugestoes', icone: 'check', desabilitado: !sugeridas.length,
        aoClicar: (e) => comCarregamento(e.currentTarget, async () => {
          const res = await api('/lancamentos/classificacao-lote', { metodo: 'POST', corpo: { lancamento_ids: sugeridas.map((l) => l.id) } });
          notificar(`${res.atualizados} lançamento(s) confirmado(s).`);
          carregarLancamentos();
        }),
      });
      const rotStatus = { pendente: ['Pendente', 'alerta'], manual: ['Manual', 'sucesso'], ia_sugerida: ['Sugerida pela IA', 'info'], ia_confirmada: ['IA confirmada', 'sucesso'] };
      lista.replaceChildren(h('div', { class: 'acoes acoes-fixas' }, confirmarTodas), tabela({
        id: 'tabela-lancamentos', legenda: `Lançamentos (${r.total})`, linhas: r.itens,
        tituloCartao: (l) => `${data(l.data)} · ${l.natureza === 'C' ? 'Crédito' : 'Débito'} ${moeda(l.valor)}`,
        colunas: [
          { titulo: 'Data', valor: (l) => data(l.data) },
          { titulo: 'Histórico', valor: (l) => l.historico },
          { titulo: 'Natureza', valor: (l) => (l.natureza === 'C' ? selo('Crédito (entrada)', 'sucesso') : selo('Débito (saída)', 'erro')) },
          { titulo: 'Valor', num: true, valor: (l) => moeda(l.valor) },
          { titulo: 'Situação', valor: (l) => h('span', {}, selo(...rotStatus[l.status_classificacao]), l.confianca_ia ? ` confiança ${pct(l.confianca_ia * 100, 0)}` : '') },
          { titulo: 'Conta', valor: (l) => {
            const c = campo({ id: `lanc-conta-${l.id}`, nome: 'conta_id', rotulo: `Conta para “${l.historico}” de ${data(l.data)}`, tipo: 'select', valor: l.conta_id, opcoes: opcoesPlano(plano) });
            c.querySelector('label').classList.add('sr-only');
            c.querySelector('select').addEventListener('change', async (e) => {
              if (!e.target.value) return;
              try {
                const res = await api(`/lancamentos/${l.id}/classificacao`, { metodo: 'PUT', corpo: { conta_id: Number(e.target.value), replicar_semelhantes: true } });
                notificar(res.replicados ? `Classificado. A mesma conta foi sugerida para ${res.replicados} lançamento(s) semelhante(s).` : 'Lançamento classificado.');
                if (res.replicados) carregarLancamentos();
              } catch (er) { notificar(er.message, 'erro'); }
            });
            return c;
          } },
        ],
      }), paginacao({ id: 'lancamentos', pagina: filtros.pagina, porPagina: 50, total: r.total, aoMudar: (p) => { filtros.pagina = p; carregarLancamentos(); } }));
    } catch (e) { erroCarga(lista, e, carregarLancamentos); }
  }
  carregarLancamentos();
}

function formularioConta(clienteId, tipo, aoSalvar) {
  const form = h('form', { id: `form-conta-${tipo}`, novalidate: true },
    h('div', { class: 'grade-2' },
      campo({ id: `conta-banco-nome-${tipo}`, nome: 'banco_nome', rotulo: 'Banco / instituição', obrigatorio: true }),
      campo({ id: `conta-banco-codigo-${tipo}`, nome: 'banco_codigo', rotulo: 'Código do banco (3 dígitos)', atributos: { inputmode: 'numeric', maxlength: '3' } }),
      campo({ id: `conta-agencia-${tipo}`, nome: 'agencia', rotulo: 'Agência' }),
      campo({ id: `conta-numero-${tipo}`, nome: 'numero_conta', rotulo: tipo === 'corrente' ? 'Conta corrente' : 'Conta de investimento' }),
      campo({ id: `conta-descricao-${tipo}`, nome: 'descricao', rotulo: 'Descrição (opcional)' })),
    botao('Salvar conta', { id: `botao-salvar-conta-${tipo}`, tipo: 'submit' }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        await api('/contas-bancarias', { metodo: 'POST', corpo: { ...dadosFormulario(form), cliente_id: clienteId, tipo } });
        notificar('Conta cadastrada.');
        aoSalvar();
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  return form;
}

// ================================================================== aplicações
export async function abaAplicacoes(painel, ctx) {
  const { id } = ctx;
  carregando(painel);
  let contas;
  let posicoes;
  try { [contas, posicoes] = await Promise.all([api(`/clientes/${id}/contas-bancarias`), api(`/clientes/${id}/aplicacoes`)]); } catch (e) { erroCarga(painel, e); return; }
  const contasAplic = contas.filter((c) => c.tipo === 'aplicacao');
  const sem = !contasAplic.length;
  painel.replaceChildren(h('h2', {}, 'Aplicações financeiras'));

  if (sem) {
    painel.append(vazio({ nivel: 'h3', titulo: 'Nenhuma conta de investimento', texto: 'Cadastre a conta de investimento para lançar os extratos mensais das aplicações (CDB, fundos, LCI/LCA, Tesouro).' }),
      h('section', { class: 'cartao', 'aria-labelledby': 'titulo-conta-aplic' }, h('h3', { id: 'titulo-conta-aplic' }, 'Cadastrar conta de investimento'),
        formularioConta(id, 'aplicacao', () => abaAplicacoes(painel, ctx))));
    return;
  }

  const form = h('form', { id: 'form-aplicacao', novalidate: true },
    h('div', { class: 'grade' },
      campo({ id: 'aplic-conta', nome: 'conta_bancaria_id', rotulo: 'Conta de investimento', tipo: 'select', obrigatorio: true, opcoes: contasAplic.map((c) => ({ valor: c.id, rotulo: `${c.banco_nome} ${c.numero_conta || ''}` })) }),
      campo({ id: 'aplic-produto', nome: 'produto', rotulo: 'Produto', obrigatorio: true, dica: 'Ex.: CDB DI 102%, Fundo RF Referenciado' }),
      campo({ id: 'aplic-tipo', nome: 'tipo_produto', rotulo: 'Tipo', tipo: 'select', obrigatorio: true, opcoes: ['cdb', 'fundo', 'lci', 'lca', 'tesouro', 'poupanca', 'outro'].map((t) => ({ valor: t, rotulo: t.toUpperCase() })) }),
      campo({ id: 'aplic-competencia', nome: 'competencia', rotulo: 'Mês de referência', tipo: 'month', obrigatorio: true }),
      campo({ id: 'aplic-saldo-inicial', nome: 'saldo_inicial', rotulo: 'Saldo inicial (R$)', tipo: 'number', obrigatorio: true, atributos: { step: '0.01', min: '0' } }),
      campo({ id: 'aplic-aplicacoes', nome: 'aplicacoes', rotulo: 'Aplicações no mês (R$)', tipo: 'number', valor: '0', atributos: { step: '0.01', min: '0' } }),
      campo({ id: 'aplic-resgates', nome: 'resgates', rotulo: 'Resgates líquidos (R$)', tipo: 'number', valor: '0', atributos: { step: '0.01', min: '0' } }),
      campo({ id: 'aplic-saldo-final', nome: 'saldo_final_bruto', rotulo: 'Saldo final bruto (R$)', tipo: 'number', obrigatorio: true, atributos: { step: '0.01', min: '0' } }),
      campo({ id: 'aplic-irrf', nome: 'irrf', rotulo: 'IRRF retido (R$)', tipo: 'number', valor: '0', atributos: { step: '0.01', min: '0' } }),
      campo({ id: 'aplic-iof', nome: 'iof', rotulo: 'IOF (R$)', tipo: 'number', valor: '0', atributos: { step: '0.01', min: '0' } }),
      campo({ id: 'aplic-taxa', nome: 'taxa_administracao', rotulo: 'Taxa de administração (R$)', tipo: 'number', valor: '0', atributos: { step: '0.01', min: '0' } }),
      campo({ id: 'aplic-cdi', nome: 'cdi_mes_percentual', rotulo: 'CDI do mês (%)', tipo: 'number', dica: 'Opcional, para calcular o % do CDI. Ex.: 0,95', atributos: { step: '0.0001', min: '0' } })),
    botao('Lançar extrato da aplicação', { id: 'botao-lancar-aplicacao', tipo: 'submit' }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = dadosFormulario(form);
    if (d.competencia) d.competencia = `${d.competencia}-01`;
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        await api('/aplicacoes', { metodo: 'POST', corpo: d });
        notificar('Extrato da aplicação lançado. Rendimentos calculados.');
        abaAplicacoes(painel, ctx);
      } catch (erro) { mostrarErros(form, erro); }
    });
  });

  painel.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-lancar-aplic' }, h('h3', { id: 'titulo-lancar-aplic' }, 'Lançar extrato mensal'), form));
  if (posicoes.length) {
    painel.append(tabela({
      id: 'tabela-aplicacoes', legenda: 'Rendimentos calculados por mês', linhas: posicoes,
      tituloCartao: (p) => `${p.produto} — ${data(p.competencia).slice(3)}`,
      colunas: [
        { titulo: 'Mês', valor: (p) => data(p.competencia).slice(3) },
        { titulo: 'Produto', valor: (p) => p.produto },
        { titulo: 'Saldo final', num: true, valor: (p) => moeda(p.saldo_final_bruto) },
        { titulo: 'Rend. bruto', num: true, valor: (p) => moeda(p.rendimento_bruto) },
        { titulo: 'IRRF + IOF', num: true, valor: (p) => moeda(Number(p.irrf) + Number(p.iof)) },
        { titulo: 'Taxa adm.', num: true, valor: (p) => moeda(p.taxa_administracao) },
        { titulo: 'Rend. líquido', num: true, valor: (p) => moeda(p.rendimento_liquido) },
        { titulo: 'Taxa bruta mês', num: true, valor: (p) => pct(p.taxa_bruta_mes * 100, 4) },
        { titulo: 'Taxa líquida a.a.', num: true, valor: (p) => pct(p.taxa_liquida_ano * 100) },
        { titulo: '% do CDI', num: true, valor: (p) => (p.percentual_cdi ? pct(p.percentual_cdi) : '—') },
        { titulo: 'Alíquota efetiva IR', num: true, valor: (p) => (p.aliquota_efetiva_ir ? pct(p.aliquota_efetiva_ir * 100) : '—') },
      ],
      acoes: (p) => [botaoIcone('lixeira', `Excluir extrato de ${p.produto} de ${data(p.competencia).slice(3)}`, async () => {
        if (!(await confirmar(`Excluir o extrato de ${p.produto}?`, { perigo: true, textoConfirmar: 'Excluir' }))) return;
        await api(`/aplicacoes/${p.id}`, { metodo: 'DELETE' });
        abaAplicacoes(painel, ctx);
      }, { id: `excluir-aplicacao-${p.id}`, perigo: true })],
    }));
  }

  // Simulador de tributos (cálculo no backend)
  const resSim = h('div', { 'aria-live': 'polite' });
  const sim = h('form', { id: 'form-simular', class: 'linha', novalidate: true },
    campo({ id: 'sim-rendimento', nome: 'rendimento', rotulo: 'Rendimento bruto (R$)', tipo: 'number', obrigatorio: true, atributos: { step: '0.01', min: '0.01' } }),
    campo({ id: 'sim-dias', nome: 'dias', rotulo: 'Prazo da aplicação (dias)', tipo: 'number', obrigatorio: true, atributos: { min: '1' } }),
    h('div', { class: 'campo' }, botao('Simular IR e IOF', { id: 'botao-simular', tipo: 'submit', variante: 'botao-secundario' })));
  sim.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const r = await api('/aplicacoes/simular-tributos', { metodo: 'POST', corpo: dadosFormulario(sim) });
      resSim.replaceChildren(h('p', { class: 'aviso aviso-info' },
        `IOF ${pct(r.aliquota_iof * 100)} = ${moeda(r.iof)} · IR ${pct(r.aliquota_ir * 100, 1)} = ${moeda(r.irrf)} · Rendimento líquido ${moeda(r.rendimento_liquido)}`));
    } catch (erro) { mostrarErros(sim, erro); }
  });
  painel.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-simulador' }, h('h3', { id: 'titulo-simulador' }, 'Simulador de resgate (tabela regressiva)'),
    h('p', { class: 'texto-suave' }, 'Para pessoa jurídica, o IRRF é antecipação do IRPJ e LCI/LCA não são isentas.'), sim, resSim));
}
