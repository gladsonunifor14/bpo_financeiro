import { api, sessao } from '../api.js';
import { h, link, selo, tabela, vazio, data } from '../ui.js';

export async function inicio(alvo) {
  const u = sessao.usuario;
  if (u.papel === 'cliente') { location.hash = `#/clientes/${u.cliente_id}`; return; }
  const [p, esc] = await Promise.all([api('/painel'), api('/escritorio')]);
  alvo.append(
    h('div', { class: 'cabecalho-pagina' }, h('h1', {}, 'Painel do escritório'),
      h('div', { class: 'acoes acoes-fixas' }, link('Novo cliente', '#/clientes/novo', { id: 'painel-novo-cliente', variante: 'botao', ic: 'mais' }))),
    h('p', { class: 'texto-suave' }, `${esc.razao_social}${esc.crc ? ` · CRC ${esc.crc}` : ''}`));

  if (!esc.crc) {
    alvo.append(h('div', { class: 'aviso aviso-alerta', role: 'status' }, h('p', {}, 'O CRC do escritório não está preenchido e não aparecerá nos relatórios. ',
      h('a', { href: '#/escritorio', id: 'painel-completar-escritorio' }, 'Completar dados do escritório'))));
  }

  if (p.clientes_ativos === 0) {
    alvo.append(vazio({
      titulo: 'Nenhum cliente cadastrado',
      texto: 'Cadastre o primeiro cliente pelo CNPJ: os dados são importados automaticamente da Receita Federal. Depois, importe notas fiscais e extratos para gerar os relatórios.',
      ctas: [link('Cadastrar primeiro cliente', '#/clientes/novo', { id: 'painel-cta-primeiro-cliente', variante: 'botao', ic: 'mais' })],
    }));
    return;
  }

  alvo.append(h('section', { 'aria-labelledby': 'titulo-resumo' }, h('h2', { id: 'titulo-resumo', class: 'sr-only' }, 'Resumo'),
    h('div', { class: 'grade' },
      kpi('Clientes ativos', String(p.clientes_ativos), h('a', { href: '#/clientes', id: 'painel-ver-clientes' }, 'Ver clientes')),
      kpi('Contratos aguardando aceite', String(p.contratos_aguardando_aceite)),
      kpi('Procurações vencendo (30 dias)', String(p.procuracoes_vencendo.length)),
      kpi('Clientes com lançamentos a revisar', String(p.lancamentos_a_revisar.length)))));

  const sec1 = h('section', { class: 'cartao', 'aria-labelledby': 'titulo-revisar' }, h('h2', { id: 'titulo-revisar' }, 'Lançamentos bancários a revisar'));
  if (p.lancamentos_a_revisar.length) {
    sec1.append(tabela({
      id: 'tabela-revisar', legenda: 'Clientes com lançamentos pendentes ou sugeridos pela IA',
      colunas: [{ titulo: 'Cliente', valor: (l) => l.cliente }, { titulo: 'Lançamentos', num: true, valor: (l) => String(l.quantidade) }],
      linhas: p.lancamentos_a_revisar,
      acoes: (l) => [link('Revisar', `#/clientes/${l.cliente_id}/extratos`, { id: `revisar-${l.cliente_id}`, variante: 'botao botao-secundario' })],
    }));
  } else sec1.append(h('p', {}, selo('Em dia', 'sucesso'), ' Nenhum lançamento pendente de revisão.'));

  const sec2 = h('section', { class: 'cartao', 'aria-labelledby': 'titulo-procuracoes' }, h('h2', { id: 'titulo-procuracoes' }, 'Procurações a renovar'));
  if (p.procuracoes_vencendo.length) {
    sec2.append(tabela({
      id: 'tabela-procuracoes-vencendo', legenda: 'Procurações vencidas ou que vencem em até 30 dias',
      colunas: [
        { titulo: 'Cliente', valor: (x) => x.cliente },
        { titulo: 'Vencimento', valor: (x) => data(x.data_fim) },
        { titulo: 'Situação', valor: (x) => (x.vencida ? selo('Vencida', 'erro') : selo('Vence em breve', 'alerta')) },
      ],
      linhas: p.procuracoes_vencendo,
    }));
  } else sec2.append(h('p', {}, selo('Em dia', 'sucesso'), ' Nenhuma procuração vencendo nos próximos 30 dias.'));
  alvo.append(h('div', { class: 'grade-2' }, sec1, sec2));
}

function kpi(rotulo, valor, extra) {
  return h('div', { class: 'kpi' }, h('p', { class: 'rotulo' }, rotulo), h('p', { class: 'valor' }, valor), extra ? h('p', { class: 'detalhe' }, extra) : null);
}
