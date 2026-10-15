// Roteador e layout. O frontend apenas exibe dados e coleta entradas; nenhuma regra de
// negócio ou cálculo financeiro é feito aqui — tudo vem pronto da API.
import { api, restaurarSessao, sessao } from './api.js';
import { h, anunciar, notificar } from './ui.js';
import * as auth from './views/auth.js';
import * as painel from './views/painel.js';
import * as clientes from './views/clientes.js';
import * as cliente from './views/cliente.js';
import * as admin from './views/admin.js';

const conteudo = document.getElementById('conteudo');
const menu = document.getElementById('menu-principal');
const botaoMenu = document.getElementById('botao-menu');

const ROTAS = [
  { padrao: /^\/login$/, publica: true, titulo: 'Entrar', render: auth.login },
  { padrao: /^\/cadastro$/, publica: true, titulo: 'Cadastrar escritório', render: auth.cadastro },
  { padrao: /^\/recuperar-senha$/, publica: true, titulo: 'Recuperar senha', render: auth.recuperar },
  { padrao: /^\/$/, titulo: 'Painel', render: painel.inicio },
  { padrao: /^\/clientes$/, titulo: 'Clientes', equipe: true, render: clientes.lista },
  { padrao: /^\/clientes\/novo$/, titulo: 'Novo cliente', equipe: true, render: clientes.formulario },
  { padrao: /^\/clientes\/(\d+)(?:\/([a-z-]+))?$/, titulo: 'Cliente', render: cliente.detalhe },
  { padrao: /^\/termos$/, titulo: 'Termos e privacidade', render: admin.termos },
  { padrao: /^\/conta$/, titulo: 'Minha conta', render: auth.minhaConta },
  { padrao: /^\/escritorio$/, titulo: 'Escritório', equipe: true, render: admin.escritorio },
  { padrao: /^\/usuarios$/, titulo: 'Usuários', adminOnly: true, render: admin.usuarios },
  { padrao: /^\/integracoes$/, titulo: 'Integrações (API)', adminOnly: true, render: admin.integracoes },
  { padrao: /^\/auditoria$/, titulo: 'Auditoria', adminOnly: true, render: admin.auditoria },
];

function itensMenu(u) {
  if (!u) return [];
  const equipe = u.papel !== 'cliente';
  return [
    { href: '#/', texto: 'Painel' },
    equipe && { href: '#/clientes', texto: 'Clientes' },
    equipe && { href: '#/escritorio', texto: 'Escritório' },
    u.papel === 'admin' && { href: '#/usuarios', texto: 'Usuários' },
    u.papel === 'admin' && { href: '#/integracoes', texto: 'Integrações' },
    u.papel === 'admin' && { href: '#/auditoria', texto: 'Auditoria' },
    { href: '#/conta', texto: 'Minha conta' },
  ].filter(Boolean);
}

function montarMenu() {
  const u = sessao.usuario;
  menu.replaceChildren();
  if (!u) { menu.hidden = true; menu.classList.remove('menu-logado'); botaoMenu.hidden = true; return; }
  menu.classList.add('menu-logado');
  botaoMenu.hidden = false;
  const atual = location.hash.replace(/^#/, '') || '/';
  for (const it of itensMenu(u)) {
    const caminho = it.href.slice(1);
    const ativo = caminho === '/' ? atual === '/' : atual.startsWith(caminho);
    menu.append(h('a', { href: it.href, id: `menu-${it.texto.toLowerCase().replace(/\s+/g, '-')}`, 'aria-current': ativo ? 'page' : undefined }, it.texto));
  }
  menu.append(
    h('span', { class: 'usuario-logado' }, `${u.nome} (${u.papel})`),
    h('button', { type: 'button', id: 'botao-sair', on: { click: sair } }, 'Sair'),
  );
}

botaoMenu.addEventListener('click', () => {
  const aberto = botaoMenu.getAttribute('aria-expanded') === 'true';
  botaoMenu.setAttribute('aria-expanded', String(!aberto));
  menu.hidden = aberto;
});

async function sair() {
  try { await api('/auth/logout', { metodo: 'POST' }); } catch { /* sessão já encerrada */ }
  sessao.limpar();
  location.hash = '#/login';
  anunciar('Você saiu do sistema.');
}

let termosVerificados = false;

async function rotear() {
  const caminho = location.hash.replace(/^#/, '') || '/';
  const rota = ROTAS.find((r) => r.padrao.test(caminho));
  if (!rota) { conteudo.replaceChildren(h('h1', {}, 'Página não encontrada'), h('p', {}, h('a', { href: '#/' }, 'Voltar ao início'))); return; }
  if (!rota.publica && !sessao.autenticado) {
    if (!(await restaurarSessao())) { location.hash = '#/login'; return; }
  }
  const u = sessao.usuario;
  if (rota.publica && u) { location.hash = '#/'; return; }
  if (u && !termosVerificados && caminho !== '/termos') {
    termosVerificados = true;
    const pend = await api('/termos/pendentes').catch(() => []);
    if (pend.length) { notificar('Antes de continuar, leia e aceite os termos atualizados.', 'info'); location.hash = '#/termos'; return; }
  }
  if (u && rota.equipe && u.papel === 'cliente') { location.hash = `#/clientes/${u.cliente_id}`; return; }
  if (u && rota.adminOnly && u.papel !== 'admin') { location.hash = '#/'; return; }

  montarMenu();
  if (window.matchMedia('(max-width: 760px)').matches) { menu.hidden = true; botaoMenu.setAttribute('aria-expanded', 'false'); }
  document.title = `${rota.titulo} · BPO Financeiro`;
  conteudo.replaceChildren();
  const params = caminho.match(rota.padrao).slice(1);
  try {
    await rota.render(conteudo, ...params);
  } catch (e) {
    conteudo.replaceChildren(h('h1', {}, rota.titulo), h('div', { class: 'aviso aviso-erro', role: 'alert' }, h('p', {}, e.message || 'Erro ao carregar a página.')));
  }
  // Move o foco para o título da nova página (anúncio para leitores de tela)
  const titulo = conteudo.querySelector('h1');
  if (titulo) { titulo.tabIndex = -1; titulo.focus({ preventScroll: false }); }
  else conteudo.focus();
}

sessao.aoMudar((u) => { if (!u) termosVerificados = false; montarMenu(); });
window.addEventListener('hashchange', rotear);
window.addEventListener('sessao-expirada', () => {
  sessao.limpar();
  notificar('Sua sessão expirou. Entre novamente.', 'alerta');
  location.hash = '#/login';
});
rotear();
