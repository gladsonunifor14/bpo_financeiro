import { api, baixar, sessao } from '../api.js';
import {
  h, abas, botao, botaoIcone, campo, carregando, cnpj, comCarregamento, confirmar, dadosFormulario, data, dataHora,
  erroCarga, moeda, mostrarErros, notificar, selo, tabela, vazio,
} from '../ui.js';
import { abaNotas, abaExtratos, abaAplicacoes } from './cliente-documentos.js';
import { abaPainelBI, abaRelatorios } from './cliente-relatorios.js';

export async function detalhe(alvo, idTexto, abaInicial) {
  const id = Number(idTexto);
  const u = sessao.usuario;
  const equipe = u.papel !== 'cliente';
  const [cli, pre, plano] = await Promise.all([api(`/clientes/${id}`), api(`/clientes/${id}/pre-requisitos`), api('/plano-contas')]);
  const ctx = { id, cli, pre, plano, equipe, irPara };

  function irPara(aba) { location.hash = `#/clientes/${id}/${aba}`; }

  const itens = [
    { id: 'painel', rotulo: 'Painel BI', render: (p) => abaPainelBI(p, ctx) },
    { id: 'notas', rotulo: 'Notas fiscais', render: (p) => abaNotas(p, ctx) },
    { id: 'extratos', rotulo: 'Extratos bancários', render: (p) => abaExtratos(p, ctx) },
    { id: 'aplicacoes', rotulo: 'Aplicações', render: (p) => abaAplicacoes(p, ctx) },
    { id: 'relatorios', rotulo: 'Relatórios', render: (p) => abaRelatorios(p, ctx) },
    { id: 'contrato', rotulo: 'Contrato', render: (p) => abaContrato(p, ctx) },
    { id: 'procuracoes', rotulo: 'Procurações', render: (p) => abaProcuracoes(p, ctx) },
    { id: 'dados', rotulo: 'Dados cadastrais', render: (p) => abaDados(p, ctx) },
  ];
  const inicial = Math.max(0, itens.findIndex((i) => i.id === abaInicial));
  const componente = abas('cliente', itens, inicial, (aba) => history.replaceState(null, '', `#/clientes/${id}/${aba}`));

  alvo.append(
    equipe ? h('nav', { class: 'migalhas', 'aria-label': 'Trilha de navegação' }, h('ol', {}, h('li', {}, h('a', { href: '#/clientes' }, 'Clientes')), h('li', { 'aria-current': 'page' }, cli.razao_social))) : null,
    h('div', { class: 'cabecalho-pagina' },
      h('div', {}, h('h1', {}, cli.nome_fantasia || cli.razao_social), h('p', { class: 'texto-suave' }, `${cli.razao_social} · CNPJ ${cnpj(cli.cnpj)}`)),
      cli.ativo ? selo('Cliente ativo', 'sucesso') : selo('Cliente inativo', 'neutro')),
    componente.elemento);
}

// ------------------------------------------------------------------ contrato
async function abaContrato(painel, { id, cli, equipe }) {
  carregando(painel);
  let contratos;
  try { contratos = await api(`/contratos?cliente_id=${id}`); } catch (e) { erroCarga(painel, e); return; }
  painel.replaceChildren(h('h2', {}, 'Contrato de prestação de serviços (adesão)'));
  const ativo = contratos.find((c) => c.status !== 'rescindido');
  const rotulos = { aguardando_aceite: ['Aguardando aceite do cliente', 'alerta'], vigente: ['Vigente', 'sucesso'], rescindido: ['Rescindido', 'neutro'] };

  if (ativo) {
    const det = await api(`/contratos/${ativo.id}`);
    const caixa = h('section', { class: 'cartao', 'aria-labelledby': 'titulo-contrato-atual' },
      h('h3', { id: 'titulo-contrato-atual' }, `Contrato nº ${det.numero} `, selo(...rotulos[det.status])),
      h('p', {}, `Honorários: ${moeda(det.valor_mensal)} · vencimento dia ${det.dia_vencimento} · início ${data(det.inicio_vigencia)}${det.fim_vigencia ? ` · fim ${data(det.fim_vigencia)}` : ''}`),
      h('div', { class: 'texto-contrato', tabindex: '0', role: 'document', 'aria-label': 'Texto integral do contrato' }, det.conteudo),
      h('p', { class: 'texto-suave' }, `Hash SHA-256 do texto: ${det.hash_sha256}`),
      det.aceito_em ? h('p', {}, `Aceito eletronicamente em ${dataHora(det.aceito_em)} (IP ${det.aceite_ip}).`) : null);
    if (det.status === 'aguardando_aceite' && !equipe) {
      const form = h('form', { id: 'form-aceite-contrato', novalidate: true },
        campo({ id: 'aceite-li-concordo', nome: 'li_e_concordo', tipo: 'checkbox', obrigatorio: true, rotulo: 'Li integralmente e concordo com os termos deste contrato de adesão.' }),
        botao('Aceitar contrato eletronicamente', { id: 'botao-aceitar-contrato', tipo: 'submit', icone: 'check' }));
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await comCarregamento(form.querySelector('[type=submit]'), async () => {
          try {
            await api(`/contratos/${det.id}/aceite`, { metodo: 'POST', corpo: { hash_sha256: det.hash_sha256, li_e_concordo: form.elements.li_e_concordo.checked } });
            notificar('Contrato aceito. Obrigado!');
            abaContrato(painel, { id, cli, equipe });
          } catch (erro) { mostrarErros(form, erro); }
        });
      });
      caixa.append(form);
    } else if (det.status === 'aguardando_aceite') {
      caixa.append(h('p', { class: 'aviso aviso-info' }, 'O aceite deve ser feito por um usuário do cliente. Cadastre-o em Usuários com o perfil “cliente”.'));
    }
    if (equipe) {
      caixa.append(botao('Rescindir contrato', {
        id: 'botao-rescindir-contrato', variante: 'botao-perigo',
        aoClicar: async () => {
          if (!(await confirmar(`Rescindir o contrato nº ${det.numero} de ${cli.razao_social}?`, { perigo: true, textoConfirmar: 'Rescindir' }))) return;
          try {
            await api(`/contratos/${det.id}/rescisao`, { metodo: 'POST', corpo: { motivo: 'Rescisão solicitada pelo escritório' } });
            notificar('Contrato rescindido.');
            abaContrato(painel, { id, cli, equipe });
          } catch (e) { notificar(e.message, 'erro'); }
        },
      }));
    }
    painel.append(caixa);
  } else if (equipe) {
    const form = h('form', { id: 'form-emitir-contrato', novalidate: true },
      h('div', { class: 'grade-2' },
        campo({ id: 'contrato-valor', nome: 'valor_mensal', rotulo: 'Honorários mensais (R$)', tipo: 'number', obrigatorio: true, atributos: { step: '0.01', min: '0.01' } }),
        campo({ id: 'contrato-dia', nome: 'dia_vencimento', rotulo: 'Dia de vencimento', tipo: 'number', obrigatorio: true, valor: 10, atributos: { min: '1', max: '28' } }),
        campo({ id: 'contrato-inicio', nome: 'inicio_vigencia', rotulo: 'Início da vigência', tipo: 'date', obrigatorio: true }),
        campo({ id: 'contrato-fim', nome: 'fim_vigencia', rotulo: 'Fim da vigência', tipo: 'date', dica: 'Deixe vazio para prazo indeterminado' })),
      botao('Emitir contrato para aceite', { id: 'botao-emitir-contrato', tipo: 'submit' }));
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await comCarregamento(form.querySelector('[type=submit]'), async () => {
        try {
          await api('/contratos', { metodo: 'POST', corpo: { ...dadosFormulario(form), cliente_id: id } });
          notificar('Contrato emitido. O cliente já pode aceitar pelo sistema.');
          abaContrato(painel, { id, cli, equipe });
        } catch (erro) { mostrarErros(form, erro); }
      });
    });
    painel.append(vazio({ titulo: 'Sem contrato vigente', texto: 'Emita o contrato de adesão a partir do modelo do escritório. O texto é preenchido com os dados oficiais de ambas as empresas.', nivel: 'h3' }),
      h('section', { class: 'cartao', 'aria-labelledby': 'titulo-emitir' }, h('h3', { id: 'titulo-emitir' }, 'Emitir contrato'), form));
  } else {
    painel.append(vazio({ titulo: 'Nenhum contrato disponível', texto: 'O escritório ainda não emitiu o seu contrato.', nivel: 'h3' }));
  }
  const historico = contratos.filter((c) => c.status === 'rescindido');
  if (historico.length) {
    painel.append(tabela({ id: 'tabela-contratos-anteriores', legenda: 'Contratos anteriores', linhas: historico,
      colunas: [{ titulo: 'Número', valor: (c) => c.numero }, { titulo: 'Valor', num: true, valor: (c) => moeda(c.valor_mensal) }, { titulo: 'Rescindido em', valor: (c) => dataHora(c.rescindido_em) }] }));
  }
}

// ------------------------------------------------------------------ procurações
const TIPOS_PROC = [
  { valor: 'ecac', rotulo: 'e-CAC (Receita Federal)' }, { valor: 'sefaz', rotulo: 'SEFAZ (estadual)' }, { valor: 'prefeitura', rotulo: 'Prefeitura (municipal)' },
  { valor: 'particular', rotulo: 'Instrumento particular' }, { valor: 'publica', rotulo: 'Escritura pública' }, { valor: 'outra', rotulo: 'Outra' },
];
const SITUACAO_PROC = { vigente: ['Vigente', 'sucesso'], vence_em_30_dias: ['Vence em até 30 dias', 'alerta'], vencida: ['Vencida', 'erro'], revogada: ['Revogada', 'neutro'], futura: ['Início futuro', 'info'] };

async function abaProcuracoes(painel, ctx) {
  const { id, equipe } = ctx;
  carregando(painel);
  let lista;
  try { lista = await api(`/procuracoes?cliente_id=${id}`); } catch (e) { erroCarga(painel, e); return; }
  painel.replaceChildren(h('h2', {}, 'Procurações'));
  if (!lista.length) {
    painel.append(vazio({ titulo: 'Nenhuma procuração registrada', nivel: 'h3',
      texto: equipe ? 'Registre as procurações (e-CAC, SEFAZ, prefeitura) para controlar vencimentos. O sistema alerta 30 dias antes.' : 'O escritório ainda não registrou procurações.' }));
  } else {
    painel.append(tabela({
      id: 'tabela-procuracoes', legenda: 'Procurações do cliente', linhas: lista,
      colunas: [
        { titulo: 'Tipo', valor: (p) => TIPOS_PROC.find((t) => t.valor === p.tipo)?.rotulo || p.tipo },
        { titulo: 'Outorgado', valor: (p) => p.outorgado_nome },
        { titulo: 'Poderes', valor: (p) => p.poderes },
        { titulo: 'Validade', valor: (p) => `${data(p.data_inicio)} a ${p.data_fim ? data(p.data_fim) : 'indeterminado'}` },
        { titulo: 'Situação', valor: (p) => selo(...SITUACAO_PROC[p.situacao]) },
      ],
      acoes: (p) => [
        p.arquivo_nome ? botaoIcone('baixar', `Baixar PDF da procuração ${p.tipo} de ${p.outorgado_nome}`, () => baixar(`/procuracoes/${p.id}/arquivo`, `procuracao-${p.id}.pdf`), { id: `baixar-procuracao-${p.id}` }) : null,
        equipe && p.situacao !== 'revogada' ? botaoIcone('revogar', `Revogar procuração ${p.tipo} de ${p.outorgado_nome}`, async () => {
          if (!(await confirmar('Revogar esta procuração? A ação fica registrada na auditoria.', { perigo: true, textoConfirmar: 'Revogar' }))) return;
          await api(`/procuracoes/${p.id}/revogar`, { metodo: 'POST' });
          notificar('Procuração revogada.');
          abaProcuracoes(painel, ctx);
        }, { id: `revogar-procuracao-${p.id}`, perigo: true }) : null,
      ].filter(Boolean),
    }));
  }
  if (!equipe) return;
  const form = h('form', { id: 'form-procuracao', novalidate: true },
    h('div', { class: 'grade-2' },
      campo({ id: 'proc-tipo', nome: 'tipo', rotulo: 'Tipo', tipo: 'select', obrigatorio: true, opcoes: TIPOS_PROC }),
      campo({ id: 'proc-outorgado', nome: 'outorgado_nome', rotulo: 'Outorgado (nome)', obrigatorio: true }),
      campo({ id: 'proc-doc', nome: 'outorgado_documento', rotulo: 'CPF/CNPJ do outorgado', obrigatorio: true }),
      campo({ id: 'proc-inicio', nome: 'data_inicio', rotulo: 'Início', tipo: 'date', obrigatorio: true }),
      campo({ id: 'proc-fim', nome: 'data_fim', rotulo: 'Validade até', tipo: 'date' }),
      campo({ id: 'proc-arquivo', nome: 'arquivo', rotulo: 'Arquivo PDF (opcional)', tipo: 'file', atributos: { accept: 'application/pdf,.pdf' } })),
    campo({ id: 'proc-poderes', nome: 'poderes', rotulo: 'Poderes outorgados', tipo: 'textarea', obrigatorio: true }),
    botao('Registrar procuração', { id: 'botao-registrar-procuracao', tipo: 'submit' }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    fd.set('cliente_id', String(id));
    if (!form.elements.arquivo.files.length) fd.delete('arquivo');
    if (!fd.get('data_fim')) fd.delete('data_fim');
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        await api('/procuracoes', { metodo: 'POST', formulario: fd });
        notificar('Procuração registrada.');
        abaProcuracoes(painel, ctx);
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  painel.append(h('section', { class: 'cartao', 'aria-labelledby': 'titulo-nova-proc' }, h('h3', { id: 'titulo-nova-proc' }, 'Registrar procuração'), form));
}

// ------------------------------------------------------------------ dados cadastrais
function abaDados(painel, { id, cli, equipe }) {
  const linhas = [
    ['Razão social', cli.razao_social], ['Nome fantasia', cli.nome_fantasia], ['CNPJ', cnpj(cli.cnpj)], ['Situação na Receita', cli.situacao_cadastral],
    ['Atividade principal (CNAE)', cli.cnae_principal], ['E-mail', cli.email], ['Telefone', cli.telefone],
    ['Endereço', [cli.logradouro, cli.numero, cli.complemento, cli.bairro].filter(Boolean).join(', ')],
    ['Município/UF', cli.municipio ? `${cli.municipio}/${cli.uf}` : null], ['CEP', cli.cep],
  ];
  const acoes = h('div', { class: 'acoes' },
    botao('Exportar meus dados (LGPD)', {
      id: 'botao-exportar-lgpd', icone: 'baixar', variante: 'botao-secundario',
      aoClicar: () => baixar(`/clientes/${id}/exportar-dados`, `dados-${cli.cnpj}.json`),
    }));
  if (equipe) {
    acoes.prepend(botao('Atualizar com dados da Receita', {
      id: 'botao-reimportar-receita', icone: 'busca', variante: 'botao-secundario',
      aoClicar: async (e) => comCarregamento(e.currentTarget, async () => {
        try { await api(`/clientes/${id}/reimportar-receita`, { metodo: 'POST' }); notificar('Dados atualizados com a Receita Federal.'); location.reload(); } catch (er) { notificar(er.message, 'erro'); }
      }),
    }));
  }
  painel.append(h('h2', {}, 'Dados cadastrais'),
    h('section', { class: 'cartao' }, h('dl', { class: 'grade-2' }, linhas.map(([k, v]) => h('div', {}, h('dt', { class: 'texto-suave' }, k), h('dd', {}, v || '—'))))), acoes);
}

