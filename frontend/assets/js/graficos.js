// Gráficos SVG acessíveis: role="img" com descrição textual + tabela de dados equivalente.
import { h, moeda, mes, tabela } from './ui.js';

const NS = 'http://www.w3.org/2000/svg';
function s(tag, attrs = {}, texto) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (texto !== undefined) el.textContent = texto;
  return el;
}

function abreviar(v) {
  const a = Math.abs(v);
  if (a >= 1e6) return `${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`;
  if (a >= 1e3) return `${(v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mil`;
  return v.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}

/**
 * Barras agrupadas por mês.
 * series: [{ nome, valores: { 'AAAA-MM': número } }]
 */
export function graficoBarras({ id, titulo, meses, series }) {
  const largura = Math.max(560, meses.length * series.length * 34 + 120);
  const altura = 280;
  const m = { topo: 16, dir: 16, base: 40, esq: 70 };
  const todos = series.flatMap((sr) => meses.map((mm) => sr.valores[mm] || 0));
  const max = Math.max(0, ...todos);
  const min = Math.min(0, ...todos);
  const faixa = max - min || 1;
  const y = (v) => m.topo + (max - v) / faixa * (altura - m.topo - m.base);
  const larguraGrupo = (largura - m.esq - m.dir) / Math.max(1, meses.length);
  const larguraBarra = Math.min(28, (larguraGrupo - 12) / series.length);

  const resumo = series.map((sr) => `${sr.nome}: ` + meses.map((mm) => `${mes(mm)} ${moeda(sr.valores[mm] || 0)}`).join(', ')).join('. ');
  const svg = s('svg', { class: 'grafico', viewBox: `0 0 ${largura} ${altura}`, role: 'img', 'aria-labelledby': `${id}-t ${id}-d`, id });
  svg.append(s('title', { id: `${id}-t` }, titulo), s('desc', { id: `${id}-d` }, resumo));

  for (let i = 0; i <= 4; i += 1) {
    const v = min + faixa * (i / 4);
    const yy = y(v);
    svg.append(s('line', { x1: m.esq, x2: largura - m.dir, y1: yy, y2: yy, class: 'grade-linha' }));
    svg.append(s('text', { x: m.esq - 8, y: yy + 4, 'text-anchor': 'end', 'aria-hidden': 'true' }, abreviar(v)));
  }
  svg.append(s('line', { x1: m.esq, x2: largura - m.dir, y1: y(0), y2: y(0), class: 'eixo' }));
  meses.forEach((mm, i) => {
    const x0 = m.esq + i * larguraGrupo + (larguraGrupo - larguraBarra * series.length) / 2;
    series.forEach((sr, j) => {
      const v = sr.valores[mm] || 0;
      const topo = Math.min(y(v), y(0));
      const r = s('rect', { x: x0 + j * larguraBarra, y: topo, width: Math.max(2, larguraBarra - 3), height: Math.max(1, Math.abs(y(v) - y(0))), class: `serie-${j + 1}` });
      r.append(s('title', {}, `${sr.nome} em ${mes(mm)}: ${moeda(v)}`));
      svg.append(r);
    });
    svg.append(s('text', { x: m.esq + i * larguraGrupo + larguraGrupo / 2, y: altura - m.base + 18, 'text-anchor': 'middle', 'aria-hidden': 'true' }, mes(mm)));
  });

  const legenda = h('ul', { class: 'legenda', 'aria-label': `Legenda: ${titulo}` },
    series.map((sr, j) => h('li', {}, h('span', { class: `amostra serie-${j + 1}`, 'aria-hidden': 'true' }), sr.nome)));
  const dados = h('details', { class: 'nao-imprimir' }, h('summary', { id: `${id}-ver-dados` }, `Ver dados do gráfico “${titulo}” em tabela`),
    tabela({
      id: `${id}-tabela`, legenda: titulo, semCartoes: true,
      colunas: [{ titulo: 'Mês', valor: (mm) => mes(mm) }, ...series.map((sr) => ({ titulo: sr.nome, num: true, valor: (mm) => moeda(sr.valores[mm] || 0) }))],
      linhas: meses,
    }));
  return h('figure', { class: 'cartao' }, h('figcaption', {}, h('h3', {}, titulo)), h('div', { class: 'tabela-rolagem', tabindex: '0', role: 'region', 'aria-label': `${titulo} (role para ver todo o gráfico)` }, svg), legenda, dados);
}
