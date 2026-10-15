import { api, baixar } from '../api.js';
import { h, botao, campo, carregando, cnpj, comCarregamento, dadosFormulario, erroCarga, mes, moeda, mostrarErros, pct, prerequisito, selo, tabela, vazio } from '../ui.js';
import { graficoBarras } from '../graficos.js';

const hojeISO = () => new Date().toISOString().slice(0, 10);
const inicioAnoISO = () => `${new Date().getFullYear()}-01-01`;

function ctasPrerequisito(ctx) {
  return [
    botao('Importar notas fiscais (XML)', { id: 'cta-bi-notas', icone: 'enviar', aoClicar: () => ctx.irPara('notas') }),
    botao('Importar extrato bancário', { id: 'cta-bi-extratos', icone: 'enviar', variante: 'botao-secundario', aoClicar: () => ctx.irPara('extratos') }),
  ];
}

function cabecalhoRelatorio(r) {
  const e = r.elaborado_por;
  return h('header', { class: 'cabecalho-relatorio' },
    h('p', {}, h('strong', {}, r.titulo)),
    h('p', {}, `${r.cliente.razao_social} — CNPJ ${cnpj(r.cliente.cnpj)}`),
    h('p', { class: 'texto-suave' }, `Período: ${r.periodo.inicio.split('-').reverse().join('/')} a ${r.periodo.fim.split('-').reverse().join('/')}`),
    h('p', { class: 'texto-suave' }, `Elaborado por ${e.razao_social} — CNPJ ${cnpj(e.cnpj)}${e.crc ? ` — CRC ${e.crc}` : ''}${e.responsavel_tecnico ? ` — Responsável técnico: ${e.responsavel_tecnico}` : ''}`));
}

function formPeriodo(prefixo, aoGerar, extra = []) {
  const form = h('form', { id: `form-periodo-${prefixo}`, class: 'linha', novalidate: true },
    campo({ id: `${prefixo}-inicio`, nome: 'inicio', rotulo: 'De', tipo: 'date', valor: inicioAnoISO(), obrigatorio: true }),
    campo({ id: `${prefixo}-fim`, nome: 'fim', rotulo: 'Até', tipo: 'date', valor: hojeISO(), obrigatorio: true }),
    ...extra);
  form.addEventListener('submit', (e) => { e.preventDefault(); aoGerar(form); });
  return form;
}

// ================================================================== painel BI (relatório gerencial)
export async function abaPainelBI(painel, ctx) {
  const { id, pre } = ctx;
  painel.append(h('h2', {}, 'Painel de indicadores'));
  if (!pre.pode_gerar_dre) {
    painel.append(vazio({ nivel: 'h3', titulo: 'Ainda não há dados para os indicadores',
      texto: 'Os painéis são montados a partir das notas fiscais e dos extratos bancários. Importe ao menos um dos dois para começar.',
      ctas: ctasPrerequisito(ctx) }));
    return;
  }
  const area = h('div', { id: 'area-bi', 'aria-live': 'polite' });
  const form = formPeriodo('bi', carregar, [h('div', { class: 'campo' }, botao('Atualizar painel', { id: 'botao-atualizar-bi', tipo: 'submit' }))]);
  painel.append(form, area);

  async function carregar() {
    const d = dadosFormulario(form);
    carregando(area, 'Calculando indicadores…');
    try {
      const r = await api(`/clientes/${id}/relatorios/gerencial?inicio=${d.inicio}&fim=${d.fim}`);
      const i = r.indicadores;
      const k = (rotulo, valor, detalhe, negativo) => h('div', { class: 'kpi' }, h('p', { class: 'rotulo' }, rotulo),
        h('p', { class: `valor${negativo ? ' negativo' : ''}` }, valor, negativo ? h('span', { class: 'sr-only' }, ' (negativo)') : null), detalhe ? h('p', { class: 'detalhe' }, detalhe) : null);
      area.replaceChildren(
        cabecalhoRelatorio(r),
        r.alertas.length ? h('section', { class: 'aviso aviso-alerta', 'aria-labelledby': 'titulo-alertas' }, h('h3', { id: 'titulo-alertas' }, `Alertas (${r.alertas.length})`),
          h('ul', {}, r.alertas.map((a) => h('li', {}, selo(a.nivel === 'alto' ? 'Prioridade alta' : 'Atenção', a.nivel === 'alto' ? 'erro' : 'alerta'), ' ', a.mensagem)))) : null,
        h('section', { 'aria-labelledby': 'titulo-kpis' }, h('h3', { id: 'titulo-kpis' }, 'Indicadores do período'),
          h('div', { class: 'grade' },
            k('Receita líquida', moeda(i.receita_liquida), `Receita bruta ${moeda(i.receita_bruta)}`),
            k('Lucro bruto', moeda(i.lucro_bruto), `Margem bruta ${pct(i.margem_bruta_pct)}`, i.lucro_bruto < 0),
            k('Resultado operacional', moeda(i.resultado_operacional), `Margem operacional ${pct(i.margem_operacional_pct)}`, i.resultado_operacional < 0),
            k('Lucro líquido', moeda(i.lucro_liquido), `Margem líquida ${pct(i.margem_liquida_pct)}`, i.lucro_liquido < 0),
            k('Saldo em caixa', moeda(i.saldo_caixa), 'Segundo os extratos importados', i.saldo_caixa < 0),
            k('Contas a receber', moeda(i.contas_a_receber), 'Duplicatas de notas emitidas a vencer'),
            k('Contas a pagar', moeda(i.contas_a_pagar), 'Duplicatas de notas recebidas a vencer'),
            k('Ticket médio', moeda(i.ticket_medio), `${i.notas_emitidas} nota(s) de venda`),
            k('Lançamentos conciliados', i.lancamentos_classificados_pct === null ? '—' : pct(i.lancamentos_classificados_pct, 1), `${i.lancamentos_total} lançamento(s) no período`))),
        graficoBarras({ id: 'grafico-resultado', titulo: 'Receita líquida × lucro líquido por mês', meses: r.serie_mensal.meses,
          series: [{ nome: 'Receita líquida', valores: r.serie_mensal.receita_liquida }, { nome: 'Lucro líquido', valores: r.serie_mensal.lucro_liquido }] }),
        h('div', { class: 'grade-2' },
          ranking('top-clientes', 'Maiores clientes (vendas)', r.top_clientes),
          ranking('top-fornecedores', 'Maiores fornecedores (compras)', r.top_fornecedores)),
        r.maiores_despesas.length ? tabela({ id: 'tabela-maiores-despesas', legenda: 'Maiores custos e despesas', linhas: r.maiores_despesas,
          colunas: [{ titulo: 'Conta', valor: (x) => `${x.codigo} ${x.nome}` }, { titulo: 'Total', num: true, valor: (x) => moeda(x.total) }] }) : null);
    } catch (e) { erroCarga(area, e, carregar); }
  }
  carregar();
}

function ranking(idTab, titulo, linhas) {
  if (!linhas.length) return h('section', { class: 'cartao' }, h('h3', {}, titulo), h('p', {}, 'Sem notas no período.'));
  return tabela({ id: `tabela-${idTab}`, legenda: titulo, linhas,
    colunas: [{ titulo: 'Nome', valor: (x) => x.nome || '—' }, { titulo: 'CNPJ/CPF', valor: (x) => cnpj(x.documento) }, { titulo: 'Total', num: true, valor: (x) => moeda(x.total) }] });
}

// ================================================================== DRE e fluxo de caixa
export function abaRelatorios(painel, ctx) {
  const { id, pre } = ctx;
  const area = h('div', { id: 'area-relatorio', 'aria-live': 'polite' });
  const idPreDre = 'pre-dre';
  const idPreFluxo = 'pre-fluxo';
  const bDre = botao('Gerar DRE', { id: 'botao-gerar-dre', tipo: 'button', desabilitado: !pre.pode_gerar_dre, descritoPor: !pre.pode_gerar_dre ? idPreDre : undefined });
  const bFluxo = botao('Gerar Fluxo de Caixa', { id: 'botao-gerar-fluxo', tipo: 'button', variante: 'botao-secundario', desabilitado: !pre.pode_gerar_fluxo_caixa, descritoPor: !pre.pode_gerar_fluxo_caixa ? idPreFluxo : undefined });
  const form = formPeriodo('relatorio', () => {}, [
    campo({ id: 'relatorio-saldo-inicial', nome: 'saldo_inicial', rotulo: 'Saldo inicial de caixa (R$)', tipo: 'number', valor: '0', dica: 'Usado no fluxo de caixa', atributos: { step: '0.01' } }),
  ]);
  bDre.addEventListener('click', () => comCarregamento(bDre, () => gerar('dre')));
  bFluxo.addEventListener('click', () => comCarregamento(bFluxo, () => gerar('fluxo-caixa')));

  painel.append(h('h2', {}, 'Relatórios'),
    h('section', { class: 'cartao', 'aria-labelledby': 'titulo-parametros' }, h('h3', { id: 'titulo-parametros' }, 'Parâmetros'), form,
      h('div', { class: 'acoes acoes-fixas' }, bDre, bFluxo),
      !pre.pode_gerar_dre ? prerequisito(idPreDre, 'A DRE precisa de notas fiscais ou extratos importados.', botao('Importar notas fiscais', { id: 'cta-dre-notas', variante: 'botao-secundario', aoClicar: () => ctx.irPara('notas') })) : null,
      !pre.pode_gerar_fluxo_caixa ? prerequisito(idPreFluxo, 'O fluxo de caixa precisa de ao menos um extrato bancário importado.', botao('Importar extrato', { id: 'cta-fluxo-extrato', variante: 'botao-secundario', aoClicar: () => ctx.irPara('extratos') })) : null,
      pre.lancamentos_a_revisar ? h('p', { class: 'aviso aviso-alerta' }, `${pre.lancamentos_a_revisar} lançamento(s) bancário(s) ainda não confirmados podem distorcer os relatórios.`) : null),
    area);

  async function gerar(tipo) {
    const d = dadosFormulario(form);
    const q = new URLSearchParams({ inicio: d.inicio, fim: d.fim });
    if (tipo === 'fluxo-caixa') q.set('saldo_inicial', d.saldo_inicial || '0');
    try {
      const r = await api(`/clientes/${id}/relatorios/${tipo}?${q}`);
      const exportar = botao('Exportar CSV', { id: `exportar-${tipo}`, icone: 'baixar', variante: 'botao-secundario',
        aoClicar: () => baixar(`/clientes/${id}/relatorios/${tipo}?${q}&formato=csv`, `${tipo}-${d.inicio}-${d.fim}.csv`) });
      const imprimir = botao('Imprimir / salvar PDF', { id: `imprimir-${tipo}`, icone: 'impressora', variante: 'botao-secundario', aoClicar: () => window.print() });
      area.replaceChildren(h('section', { class: 'cartao', 'aria-labelledby': `titulo-${tipo}` },
        h('h3', { id: `titulo-${tipo}`, class: 'sr-only' }, r.titulo), cabecalhoRelatorio(r),
        h('div', { class: 'acoes' }, exportar, imprimir),
        tipo === 'dre' ? renderDre(r) : renderFluxo(r)));
      area.querySelector('h3').tabIndex = -1;
      area.querySelector('h3').focus();
    } catch (e) { mostrarErros(form, e); }
  }
}

function celula(v) {
  return h('td', { class: `num${v < 0 ? ' negativo' : ''}` }, moeda(v));
}

function renderDre(r) {
  const corpo = [];
  for (const l of r.linhas) {
    corpo.push(h('tr', { class: l.tipo === 'grupo' ? '' : l.tipo }, h('th', { scope: 'row' }, l.rotulo), r.meses.map((m) => celula(l.valores[m])), celula(l.total)));
    for (const c of l.contas) corpo.push(h('tr', { class: 'detalhe' }, h('th', { scope: 'row' }, `${c.codigo} ${c.nome}`), r.meses.map((m) => celula(c.valores[m])), celula(c.total)));
  }
  const origem = Object.entries(r.origem_valores).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${moeda(v)}`).join(' · ');
  return h('div', {},
    h('p', { class: 'dica-rolagem', id: 'dre-dica' }, 'Role a tabela horizontalmente para ver todos os meses.'),
    h('div', { class: 'tabela-rolagem', tabindex: '0', role: 'region', 'aria-labelledby': 'dre-legenda', 'aria-describedby': 'dre-dica' },
      h('table', { id: 'tabela-dre' },
        h('caption', { id: 'dre-legenda' }, 'Demonstração do Resultado por mês (valores em R$)'),
        h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Descrição'), r.meses.map((m) => h('th', { scope: 'col', class: 'num' }, mes(m))), h('th', { scope: 'col', class: 'num' }, 'Total'))),
        h('tbody', {}, corpo))),
    h('p', { class: 'texto-suave' }, `Origem dos valores: ${origem || 'sem movimentação'}.`));
}

function renderFluxo(r) {
  return h('div', {},
    r.lancamentos_nao_classificados ? h('p', { class: 'aviso aviso-alerta' }, `${r.lancamentos_nao_classificados} lançamento(s) sem classificação aparecem como “Não classificado”.`) : null,
    graficoBarras({ id: 'grafico-fluxo', titulo: 'Entradas × saídas por mês', meses: r.meses,
      series: [{ nome: 'Entradas', valores: Object.fromEntries(r.realizado.map((m) => [m.mes, m.entradas])) },
        { nome: 'Saídas', valores: Object.fromEntries(r.realizado.map((m) => [m.mes, m.saidas])) }] }),
    tabela({ id: 'tabela-fluxo-realizado', legenda: 'Fluxo de caixa realizado', linhas: r.realizado, tituloCartao: (m) => mes(m.mes),
      colunas: [
        { titulo: 'Mês', valor: (m) => mes(m.mes) },
        { titulo: 'Saldo inicial', num: true, valor: (m) => moeda(m.saldo_inicial) },
        { titulo: 'Entradas', num: true, valor: (m) => moeda(m.entradas) },
        { titulo: 'Saídas', num: true, valor: (m) => moeda(m.saidas) },
        { titulo: 'Variação', num: true, valor: (m) => moeda(m.variacao) },
        { titulo: 'Saldo final', num: true, valor: (m) => moeda(m.saldo_final) },
      ] }),
    tabela({ id: 'tabela-fluxo-projetado', legenda: 'Fluxo projetado (duplicatas das notas fiscais)', linhas: r.projetado, tituloCartao: (m) => mes(m.mes),
      colunas: [
        { titulo: 'Mês', valor: (m) => mes(m.mes) },
        { titulo: 'A receber', num: true, valor: (m) => moeda(m.a_receber) },
        { titulo: 'A pagar', num: true, valor: (m) => moeda(m.a_pagar) },
        { titulo: 'Saldo projetado', num: true, valor: (m) => moeda(m.saldo_projetado) },
      ] }),
    r.detalhamento.length ? tabela({ id: 'tabela-fluxo-contas', legenda: 'Entradas e saídas por conta', linhas: r.detalhamento,
      colunas: [
        { titulo: 'Conta', valor: (x) => `${x.conta_codigo} ${x.conta_nome}` },
        { titulo: 'Natureza', valor: (x) => (x.natureza === 'entrada' ? 'Entrada' : 'Saída') },
        { titulo: 'Total', num: true, valor: (x) => moeda(x.total) },
      ] }) : null);
}
