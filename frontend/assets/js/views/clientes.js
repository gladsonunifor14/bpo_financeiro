import { api } from '../api.js';
import {
  h, botao, campo, carregando, cnpj, comCarregamento, dadosFormulario, erroCarga, link, mostrarErros, notificar,
  paginacao, selo, tabela, vazio,
} from '../ui.js';

const REGIMES = [
  { valor: '', rotulo: 'Selecione…' }, { valor: 'simples', rotulo: 'Simples Nacional' }, { valor: 'presumido', rotulo: 'Lucro Presumido' },
  { valor: 'real', rotulo: 'Lucro Real' }, { valor: 'mei', rotulo: 'MEI' },
];

export async function lista(alvo) {
  let pagina = 1;
  let busca = '';
  const resultado = h('div', { id: 'resultado-clientes', 'aria-live': 'polite' });
  const form = h('form', { id: 'form-busca-clientes', role: 'search', class: 'linha' },
    campo({ id: 'busca-clientes', nome: 'busca', rotulo: 'Buscar por nome ou CNPJ', tipo: 'search' }),
    h('div', { class: 'campo' }, botao('Buscar', { id: 'botao-buscar-clientes', tipo: 'submit', icone: 'busca', variante: 'botao-secundario' })));
  form.addEventListener('submit', (e) => { e.preventDefault(); busca = dadosFormulario(form).busca || ''; pagina = 1; carregar(); });

  alvo.append(h('div', { class: 'cabecalho-pagina' }, h('h1', {}, 'Clientes'),
    h('div', { class: 'acoes acoes-fixas' }, link('Novo cliente', '#/clientes/novo', { id: 'botao-novo-cliente', variante: 'botao', ic: 'mais' }))),
  form, resultado);

  async function carregar() {
    carregando(resultado);
    try {
      const q = new URLSearchParams({ pagina, por_pagina: 20 });
      if (busca) q.set('busca', busca);
      const r = await api(`/clientes?${q}`);
      if (!r.total) {
        resultado.replaceChildren(busca
          ? vazio({ titulo: 'Nenhum cliente encontrado', texto: `Nenhum resultado para “${busca}”.`, ctas: [botao('Limpar busca', { id: 'limpar-busca', variante: 'botao-secundario', aoClicar: () => { form.reset(); busca = ''; carregar(); } })] })
          : vazio({ titulo: 'Nenhum cliente cadastrado', texto: 'Comece cadastrando um cliente pelo CNPJ.', ctas: [link('Cadastrar cliente', '#/clientes/novo', { id: 'cta-cadastrar-cliente', variante: 'botao', ic: 'mais' })] }));
        return;
      }
      resultado.replaceChildren(
        tabela({
          id: 'tabela-clientes', legenda: `Clientes (${r.total})`,
          colunas: [
            { titulo: 'Razão social', valor: (c) => h('a', { href: `#/clientes/${c.id}`, id: `link-cliente-${c.id}` }, c.razao_social) },
            { titulo: 'CNPJ', valor: (c) => cnpj(c.cnpj) },
            { titulo: 'Regime', valor: (c) => (REGIMES.find((x) => x.valor === c.regime_tributario)?.rotulo || '—') },
            { titulo: 'Município/UF', valor: (c) => (c.municipio ? `${c.municipio}/${c.uf}` : '—') },
            { titulo: 'Situação', valor: (c) => (c.ativo ? selo('Ativo', 'sucesso') : selo('Inativo', 'neutro')) },
          ],
          linhas: r.itens,
          acoes: (c) => [link('Abrir', `#/clientes/${c.id}`, { id: `abrir-cliente-${c.id}`, variante: 'botao botao-secundario' })],
        }),
        paginacao({ id: 'clientes', pagina, porPagina: 20, total: r.total, aoMudar: (p) => { pagina = p; carregar(); } }));
    } catch (e) { erroCarga(resultado, e, carregar); }
  }
  carregar();
}

export function formulario(alvo) {
  const previa = h('div', { id: 'previa-receita', 'aria-live': 'polite' });
  const form = h('form', { id: 'form-cliente', novalidate: true });
  const cnpjCampo = campo({ id: 'cliente-cnpj', nome: 'cnpj', rotulo: 'CNPJ', obrigatorio: true, dica: 'Com ou sem pontuação. Aceita o novo CNPJ alfanumérico.', atributos: { maxlength: '18' } });
  const botaoBuscar = botao('Buscar na Receita Federal', { id: 'botao-buscar-receita', icone: 'busca', variante: 'botao-secundario' });
  botaoBuscar.addEventListener('click', () => comCarregamento(botaoBuscar, async () => {
    const valor = form.elements.cnpj.value.trim();
    if (!valor) { mostrarErros(form, { message: 'Informe o CNPJ.', campos: { cnpj: 'Informe o CNPJ para buscar' } }); return; }
    try {
      const d = await api(`/cnpj/${encodeURIComponent(valor.replace(/[^0-9A-Za-z]/g, ''))}`);
      for (const k of ['razao_social', 'nome_fantasia', 'email']) if (d[k] && form.elements[k]) form.elements[k].value = d[k];
      previa.replaceChildren(h('div', { class: 'aviso aviso-sucesso' },
        h('p', {}, h('strong', {}, d.razao_social), ` — situação: ${d.situacao_cadastral || 'não informada'}`),
        h('p', {}, [d.logradouro, d.numero, d.bairro, d.municipio && `${d.municipio}/${d.uf}`].filter(Boolean).join(', ')),
        h('p', { class: 'texto-suave' }, `Fonte: ${d.fonte}. Os dados serão gravados ao salvar.`)));
    } catch (e) {
      previa.replaceChildren(h('div', { class: 'aviso aviso-alerta', role: 'alert' }, h('p', {}, e.message),
        h('p', {}, 'Você pode preencher a razão social manualmente e desmarcar a importação.')));
    }
  }));
  form.append(
    h('div', { class: 'linha' }, cnpjCampo, h('div', { class: 'campo' }, botaoBuscar)), previa,
    campo({ id: 'cliente-importar', nome: 'importar_receita', tipo: 'checkbox', valor: true, rotulo: 'Importar dados oficiais da Receita Federal ao salvar' }),
    h('div', { class: 'grade-2' },
      campo({ id: 'cliente-razao', nome: 'razao_social', rotulo: 'Razão social', dica: 'Preenchida automaticamente pela Receita' }),
      campo({ id: 'cliente-fantasia', nome: 'nome_fantasia', rotulo: 'Nome fantasia' }),
      campo({ id: 'cliente-email', nome: 'email', rotulo: 'E-mail', tipo: 'email' }),
      campo({ id: 'cliente-telefone', nome: 'telefone', rotulo: 'Telefone', tipo: 'tel' }),
      campo({ id: 'cliente-regime', nome: 'regime_tributario', rotulo: 'Regime tributário', tipo: 'select', opcoes: REGIMES })),
    h('div', { class: 'acoes acoes-fixas' }, botao('Salvar cliente', { id: 'botao-salvar-cliente', tipo: 'submit' }),
      link('Cancelar', '#/clientes', { id: 'cancelar-cliente' })));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        const c = await api('/clientes', { metodo: 'POST', corpo: dadosFormulario(form) });
        notificar(`Cliente ${c.razao_social} cadastrado.`);
        location.hash = `#/clientes/${c.id}`;
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  alvo.append(
    h('nav', { class: 'migalhas', 'aria-label': 'Trilha de navegação' }, h('ol', {}, h('li', {}, h('a', { href: '#/clientes' }, 'Clientes')), h('li', { 'aria-current': 'page' }, 'Novo cliente'))),
    h('h1', {}, 'Novo cliente'), h('div', { class: 'cartao' }, form));
}
