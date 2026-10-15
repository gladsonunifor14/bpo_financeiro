// Componentes de interface acessíveis. Todo texto vindo da API é inserido com textContent
// (nunca innerHTML), o que elimina XSS por conteúdo de documentos/extratos.

let seq = 0;
export const novoId = (prefixo = 'id') => `${prefixo}-${++seq}`;

export function h(tag, attrs = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'on') for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k in el && typeof v !== 'string' && !k.startsWith('aria')) el[k] = v;
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  anexar(el, filhos);
  return el;
}

function anexar(el, filhos) {
  for (const f of filhos.flat(Infinity)) {
    if (f === null || f === undefined || f === false) continue;
    el.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
}

const ICONES = {
  mais: 'M12 5v14M5 12h14',
  lixeira: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  editar: 'M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4',
  baixar: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  enviar: 'M12 20V9M7 14l5-5 5 5M5 4h14',
  olho: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z',
  busca: 'M11 4a7 7 0 100 14 7 7 0 000-14zM20 20l-4-4',
  ia: 'M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2M12 8a4 4 0 100 8 4 4 0 000-8z',
  check: 'M5 12l5 5L20 7',
  sair: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
  impressora: 'M6 9V3h12v6M6 18H4v-7h16v7h-2M8 14h8v7H8z',
  revogar: 'M5 5l14 14M12 3a9 9 0 110 18 9 9 0 010-18z',
};

export function icone(nome) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  const p = document.createElementNS(ns, 'path');
  p.setAttribute('d', ICONES[nome] || '');
  svg.append(p);
  return svg;
}

// ------------------------------------------------------------------ botões
export function botao(texto, { id, icone: ic, variante = '', tipo = 'button', aoClicar, rotulo, desabilitado, descritoPor } = {}) {
  return h('button', {
    type: tipo, id, class: `botao ${variante}`.trim(), 'aria-label': rotulo, title: rotulo,
    disabled: desabilitado, 'aria-describedby': descritoPor, on: aoClicar ? { click: aoClicar } : undefined,
  }, ic ? icone(ic) : null, texto);
}

/** Botão só com ícone: exige rótulo específico, ex.: "Excluir nota 123 de ACME". */
export function botaoIcone(ic, rotulo, aoClicar, { id, perigo } = {}) {
  return h('button', { type: 'button', id, class: `botao botao-icone${perigo ? ' perigo' : ''}`, 'aria-label': rotulo, title: rotulo, on: { click: aoClicar } }, icone(ic));
}

export function link(texto, href, { id, variante = 'botao botao-secundario', ic } = {}) {
  return h('a', { href, id, class: variante }, ic ? icone(ic) : null, texto);
}

export async function comCarregamento(btn, fn) {
  if (btn.getAttribute('aria-busy') === 'true') return undefined;
  btn.setAttribute('aria-busy', 'true');
  btn.disabled = true;
  try { return await fn(); } finally { btn.removeAttribute('aria-busy'); btn.disabled = false; }
}

// ------------------------------------------------------------------ campos
/**
 * Campo rotulado com dica e mensagem de erro associadas via aria-describedby.
 * tipo: text|email|password|date|number|select|textarea|checkbox|file
 */
export function campo({ id, nome, rotulo, tipo = 'text', obrigatorio, dica, valor, opcoes, autocomplete, atributos = {} }) {
  const idDica = dica ? `${id}-dica` : null;
  const idErro = `${id}-erro`;
  const descritos = [idDica, idErro].filter(Boolean).join(' ');
  const base = { id, name: nome || id, required: obrigatorio, 'aria-required': obrigatorio ? 'true' : undefined, 'aria-describedby': descritos, autocomplete, ...atributos };
  const erro = h('p', { id: idErro, class: 'mensagem-erro', 'aria-live': 'polite' });
  if (tipo === 'checkbox') {
    const input = h('input', { ...base, type: 'checkbox', checked: !!valor });
    return h('div', { class: 'caixa-selecao' }, input, h('div', {}, h('label', { for: id }, rotulo), dica ? h('p', { id: idDica, class: 'dica' }, dica) : null, erro));
  }
  let controle;
  if (tipo === 'select') {
    controle = h('select', base, (opcoes || []).map((o) => h('option', { value: o.valor, selected: String(o.valor) === String(valor ?? '') }, o.rotulo)));
  } else if (tipo === 'textarea') {
    controle = h('textarea', base);
    controle.value = valor ?? '';
  } else {
    controle = h('input', { ...base, type: tipo });
    if (valor !== undefined && valor !== null && tipo !== 'file') controle.value = valor;
  }
  return h('div', { class: 'campo' },
    h('label', { for: id }, rotulo, obrigatorio ? h('span', { class: 'obrigatorio', 'aria-hidden': 'true' }, ' *') : null),
    dica ? h('p', { id: idDica, class: 'dica' }, dica) : null,
    controle, erro);
}

export function dadosFormulario(form) {
  const dados = {};
  for (const el of form.elements) {
    if (!el.name || el.type === 'submit' || el.type === 'button' || el.type === 'file') continue;
    if (el.type === 'checkbox') dados[el.name] = el.checked;
    else if (el.value !== '') dados[el.name] = el.value.trim();
  }
  return dados;
}

export function limparErros(form) {
  form.querySelectorAll('[aria-invalid="true"]').forEach((el) => el.removeAttribute('aria-invalid'));
  form.querySelectorAll('.mensagem-erro').forEach((el) => { el.textContent = ''; });
  form.querySelector('.resumo-erros')?.remove();
}

/** Mostra erros da API nos campos (aria-invalid + mensagem associada) e um resumo com links. */
export function mostrarErros(form, erro) {
  limparErros(form);
  const itens = [];
  for (const [nome, msg] of Object.entries(erro.campos || {})) {
    const el = form.elements.namedItem(nome);
    if (!el || !el.id) continue;
    el.setAttribute('aria-invalid', 'true');
    const alvo = document.getElementById(`${el.id}-erro`);
    if (alvo) alvo.textContent = msg;
    const rotulo = form.querySelector(`label[for="${el.id}"]`)?.textContent.replace(' *', '') || nome;
    itens.push(h('li', {}, h('a', { href: `#${el.id}`, on: { click: (e) => { e.preventDefault(); el.focus(); } } }, `${rotulo}: ${msg}`)));
  }
  const resumo = h('div', { class: 'aviso aviso-erro resumo-erros', role: 'alert', tabindex: '-1' },
    h('p', {}, h('strong', {}, erro.message)), itens.length ? h('ul', {}, itens) : null);
  form.prepend(resumo);
  const primeiro = form.querySelector('[aria-invalid="true"]');
  (primeiro || resumo).focus();
}

// ------------------------------------------------------------------ anúncios
export function anunciar(msg, urgente = false) {
  const alvo = document.getElementById(urgente ? 'anuncio-urgente' : 'anuncio-educado');
  alvo.textContent = '';
  setTimeout(() => { alvo.textContent = msg; }, 50);
}

export function notificar(msg, tipo = 'sucesso') {
  anunciar(msg, tipo === 'erro');
  const caixa = document.getElementById('notificacoes');
  const n = h('div', { class: `aviso aviso-${tipo}` }, h('p', {}, msg));
  caixa.append(n);
  while (caixa.children.length > 3) caixa.firstElementChild.remove();
  setTimeout(() => n.remove(), 6000);
}

export function selo(texto, tipo = 'neutro') {
  return h('span', { class: `selo selo-${tipo}` }, texto);
}

/** Estado vazio com chamadas para ação que cumprem o pré-requisito. */
export function vazio({ titulo, texto, ctas = [], nivel = 'h2' }) {
  return h('section', { class: 'vazio', 'aria-label': titulo },
    h(nivel, {}, titulo), texto ? h('p', {}, texto) : null,
    ctas.length ? h('div', { class: 'acoes' }, ctas) : null);
}

/** Explica por que uma operação está desabilitada; use o id em aria-describedby do botão. */
export function prerequisito(id, texto, cta) {
  return h('p', { id, class: 'prerequisito' }, texto, cta ? [' ', cta] : null);
}

// ------------------------------------------------------------------ formatação
const moedaFmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
export const moeda = (v) => moedaFmt.format(Number(v || 0));
export const numero = (v, casas = 2) => Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
export const pct = (v, casas = 2) => (v === null || v === undefined ? '—' : `${numero(Number(v), casas)}%`);
export function data(iso) {
  if (!iso) return '—';
  const [a, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}
export function dataHora(iso) {
  return iso ? new Date(iso).toLocaleString('pt-BR') : '—';
}
export function cnpj(c) {
  if (!c || c.length !== 14) return c || '—';
  return `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}`;
}
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
export function mes(aaaamm) {
  const [a, m] = aaaamm.split('-');
  return `${MESES[Number(m) - 1]}/${a.slice(2)}`;
}

// ------------------------------------------------------------------ tabela responsiva
/**
 * Em telas largas exibe <table> rolável (com dica de rolagem); em telas estreitas, cartões.
 * colunas: [{ titulo, valor: (linha) => string|Node, num?: bool }]
 */
export function tabela({ id, legenda, colunas, linhas, tituloCartao, acoes, semCartoes = false }) {
  const corpo = linhas.map((l) => h('tr', {},
    colunas.map((c, i) => (i === 0 ? h('th', { scope: 'row', class: c.num ? 'num' : undefined }, c.valor(l)) : h('td', { class: c.num ? 'num' : undefined }, c.valor(l)))),
    acoes ? h('td', {}, h('div', { class: 'acoes' }, acoes(l))) : null));
  const idDica = `${id}-dica`;
  const t = h('div', { class: 'tabela-rolagem', tabindex: '0', role: 'region', 'aria-labelledby': `${id}-legenda`, 'aria-describedby': idDica },
    h('table', { id },
      h('caption', { id: `${id}-legenda` }, legenda),
      h('thead', {}, h('tr', {}, colunas.map((c) => h('th', { scope: 'col', class: c.num ? 'num' : undefined }, c.titulo)), acoes ? h('th', { scope: 'col' }, 'Ações') : null)),
      h('tbody', {}, corpo)));
  const dica = h('p', { id: idDica, class: 'dica-rolagem' }, 'Role a tabela horizontalmente para ver todas as colunas.');
  if (semCartoes) return h('div', { class: 'tabela-somente' }, dica, t);
  const cartoes = h('ul', { class: 'lista-cartoes', 'aria-label': legenda },
    linhas.map((l) => h('li', {},
      h('h3', {}, tituloCartao ? tituloCartao(l) : colunas[0].valor(l)),
      h('dl', {}, colunas.slice(tituloCartao ? 0 : 1).map((c) => [h('dt', {}, c.titulo), h('dd', {}, c.valor(l))])),
      acoes ? h('div', { class: 'acoes' }, acoes(l)) : null)));
  sufixarIds(cartoes, '-cartao');
  return h('div', { class: 'tabela-responsiva' }, t, cartoes);
}

/** Os cartões repetem os controles da tabela: renomeia ids (e referências) para mantê-los únicos. */
function sufixarIds(raiz, sufixo) {
  const refs = ['for', 'aria-describedby', 'aria-labelledby', 'aria-controls'];
  raiz.querySelectorAll('*').forEach((el) => {
    if (el.id) el.id += sufixo;
    for (const a of refs) {
      const v = el.getAttribute(a);
      if (v) el.setAttribute(a, v.split(/\s+/).map((x) => x + sufixo).join(' '));
    }
  });
}

export function paginacao({ id, pagina, porPagina, total, aoMudar }) {
  const paginas = Math.max(1, Math.ceil(total / porPagina));
  return h('nav', { class: 'paginacao', 'aria-label': `Paginação ${id}` },
    h('p', { class: 'texto-suave', id: `${id}-info` }, `Página ${pagina} de ${paginas} · ${total} registro(s)`),
    botao('Anterior', { id: `${id}-anterior`, variante: 'botao-secundario', desabilitado: pagina <= 1, aoClicar: () => aoMudar(pagina - 1) }),
    botao('Próxima', { id: `${id}-proxima`, variante: 'botao-secundario', desabilitado: pagina >= paginas, aoClicar: () => aoMudar(pagina + 1) }));
}

// ------------------------------------------------------------------ abas (padrão WAI-ARIA)
export function abas(id, itens, ativaInicial = 0, aoMudar) {
  const lista = h('div', { class: 'abas', role: 'tablist', 'aria-label': 'Seções' });
  const paineis = [];
  const botoes = itens.map((it, i) => {
    const b = h('button', {
      type: 'button', role: 'tab', id: `${id}-aba-${it.id}`, 'aria-controls': `${id}-painel-${it.id}`,
      'aria-selected': i === ativaInicial ? 'true' : 'false', tabindex: i === ativaInicial ? '0' : '-1',
    }, it.rotulo);
    const painel = h('section', { role: 'tabpanel', id: `${id}-painel-${it.id}`, 'aria-labelledby': b.id, tabindex: '0', hidden: i !== ativaInicial });
    paineis.push(painel);
    b.addEventListener('click', () => ativar(i, true));
    b.addEventListener('keydown', (e) => {
      const n = itens.length;
      const alvo = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
      if (alvo !== undefined) { e.preventDefault(); ativar(alvo, true); botoes[alvo].focus(); }
    });
    return b;
  });
  lista.append(...botoes);
  const carregadas = new Set();
  function ativar(i, usuario) {
    botoes.forEach((b, j) => { b.setAttribute('aria-selected', String(i === j)); b.tabIndex = i === j ? 0 : -1; paineis[j].hidden = i !== j; });
    if (!carregadas.has(i)) { carregadas.add(i); itens[i].render(paineis[i]); }
    if (usuario && aoMudar) aoMudar(itens[i].id);
  }
  ativar(ativaInicial, false);
  return { elemento: h('div', {}, lista, paineis), recarregar: (idAba) => {
    const i = itens.findIndex((it) => it.id === idAba);
    paineis[i].replaceChildren(); itens[i].render(paineis[i]);
  } };
}

// ------------------------------------------------------------------ diálogo modal
export function dialogo({ titulo, conteudo, acoes = [], id = novoId('dialogo') }) {
  const anterior = document.activeElement;
  const tituloId = `${id}-titulo`;
  const d = h('dialog', { id, 'aria-labelledby': tituloId, 'aria-modal': 'true' },
    h('div', { class: 'dialogo-corpo' }, h('h2', { id: tituloId }, titulo), conteudo),
    h('div', { class: 'dialogo-acoes' }, acoes));
  document.body.append(d);
  d.addEventListener('close', () => { d.remove(); anterior?.focus?.(); });
  d.showModal();
  return d;
}

export function confirmar(mensagem, { titulo = 'Confirmar ação', textoConfirmar = 'Confirmar', perigo = false } = {}) {
  return new Promise((resolver) => {
    let d;
    const cancelar = botao('Cancelar', { id: 'dialogo-cancelar', variante: 'botao-secundario', aoClicar: () => { resolver(false); d.close(); } });
    const ok = botao(textoConfirmar, { id: 'dialogo-confirmar', variante: perigo ? 'botao-perigo' : '', aoClicar: () => { resolver(true); d.close(); } });
    d = dialogo({ titulo, conteudo: h('p', {}, mensagem), acoes: [cancelar, ok] });
    d.addEventListener('cancel', () => resolver(false));
    cancelar.focus();
  });
}

export function carregando(alvo, texto = 'Carregando…') {
  alvo.replaceChildren(h('p', { class: 'carregando', role: 'status' }, texto));
}

export function erroCarga(alvo, erro, tentarNovamente) {
  alvo.replaceChildren(h('div', { class: 'aviso aviso-erro', role: 'alert' },
    h('p', {}, erro.message || 'Falha ao carregar.'),
    tentarNovamente ? botao('Tentar novamente', { variante: 'botao-secundario', aoClicar: tentarNovamente }) : null));
}
