import { api, sessao, ErroApi } from '../api.js';
import { h, botao, campo, comCarregamento, dadosFormulario, limparErros, mostrarErros, notificar, anunciar } from '../ui.js';

const REGRA_SENHA = 'Mínimo de 10 caracteres, com letra maiúscula, minúscula, número e caractere especial.';

function formularioOTP(desafio, { finalidade, aoConcluir }) {
  const form = h('form', { id: `form-otp-${finalidade}`, novalidate: true },
    h('div', { class: 'aviso aviso-info', role: 'status' }, h('p', {}, desafio.mensagem),
      h('p', {}, `O código expira em ${Math.round(desafio.expira_em_segundos / 60)} minutos.`)),
    campo({ id: `otp-codigo-${finalidade}`, nome: 'codigo', rotulo: 'Código de verificação (6 dígitos)', obrigatorio: true,
      autocomplete: 'one-time-code', atributos: { inputmode: 'numeric', pattern: '[0-9]{6}', maxlength: '6', class: 'codigo-otp' } }),
    finalidade === 'recuperacao'
      ? campo({ id: 'nova-senha-recuperacao', nome: 'nova_senha', rotulo: 'Nova senha', tipo: 'password', obrigatorio: true, autocomplete: 'new-password', dica: REGRA_SENHA })
      : null,
    h('div', { class: 'acoes' }, botao(finalidade === 'login' ? 'Verificar e entrar' : 'Redefinir senha', { id: `botao-verificar-${finalidade}`, tipo: 'submit' })));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const dados = dadosFormulario(form);
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        await aoConcluir({ ...dados, desafio_id: desafio.desafio_id });
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  return form;
}

export function login(alvo) {
  const etapa = h('div', {});
  const form = h('form', { id: 'form-login', novalidate: true },
    campo({ id: 'login-email', nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true, autocomplete: 'username' }),
    campo({ id: 'login-senha', nome: 'senha', rotulo: 'Senha', tipo: 'password', obrigatorio: true, autocomplete: 'current-password' }),
    h('div', { class: 'acoes' }, botao('Continuar', { id: 'botao-login', tipo: 'submit' }),
      h('a', { href: '#/recuperar-senha', id: 'link-esqueci-senha' }, 'Esqueci minha senha')));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    limparErros(form);
    const dados = dadosFormulario(form);
    const faltando = {};
    if (!dados.email) faltando.email = 'Informe o e-mail';
    if (!dados.senha) faltando.senha = 'Informe a senha';
    if (Object.keys(faltando).length) { mostrarErros(form, Object.assign(new ErroApi(422, 'Preencha os campos obrigatórios.'), { campos: faltando })); return; }
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        const desafio = await api('/auth/login', { metodo: 'POST', corpo: dados });
        etapa.replaceChildren(h('h2', {}, 'Etapa 2 de 2: código enviado por e-mail'), formularioOTP(desafio, { finalidade: 'login', aoConcluir: entrar }));
        etapa.querySelector('input').focus();
        anunciar('Código enviado para o seu e-mail. Digite os 6 dígitos.');
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  etapa.append(h('h2', {}, 'Etapa 1 de 2: e-mail e senha'), form);
  alvo.append(h('div', { class: 'cartao cartao-estreito' },
    h('h1', {}, 'Entrar no BPO Financeiro'),
    h('p', { class: 'texto-suave' }, 'Acesso protegido por senha e código de verificação enviado ao seu e-mail.'),
    etapa,
    h('p', {}, 'Escritório ainda sem conta? ', h('a', { href: '#/cadastro', id: 'link-cadastro' }, 'Cadastre seu escritório'))));
}

async function entrar(dados) {
  const r = await api('/auth/otp/verificar', { metodo: 'POST', corpo: { desafio_id: dados.desafio_id, codigo: dados.codigo } });
  sessao.definir(r.access_token, r.usuario);
  notificar(`Bem-vindo(a), ${r.usuario.nome}.`);
  location.hash = r.usuario.papel === 'cliente' ? `#/clientes/${r.usuario.cliente_id}` : '#/';
}

export function cadastro(alvo) {
  const etapa = h('div', {});
  const form = h('form', { id: 'form-cadastro', novalidate: true },
    h('fieldset', {}, h('legend', {}, 'Escritório'),
      campo({ id: 'cadastro-cnpj', nome: 'cnpj', rotulo: 'CNPJ do escritório', obrigatorio: true, dica: 'Os dados oficiais (razão social e endereço) serão importados da Receita Federal. Aceita CNPJ alfanumérico.', atributos: { inputmode: 'text', maxlength: '18' } }),
      campo({ id: 'cadastro-crc', nome: 'crc', rotulo: 'Registro CRC', dica: 'Exibido nos relatórios como responsável técnico. Ex.: CE-012345/O' }),
      campo({ id: 'cadastro-razao', nome: 'razao_social', rotulo: 'Razão social (somente se a Receita estiver indisponível)' })),
    h('fieldset', {}, h('legend', {}, 'Administrador'),
      campo({ id: 'cadastro-nome', nome: 'nome', rotulo: 'Seu nome completo', obrigatorio: true, autocomplete: 'name' }),
      campo({ id: 'cadastro-email', nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true, autocomplete: 'email' }),
      campo({ id: 'cadastro-senha', nome: 'senha', rotulo: 'Senha', tipo: 'password', obrigatorio: true, autocomplete: 'new-password', dica: REGRA_SENHA })),
    campo({ id: 'cadastro-aceite', nome: 'aceite_termos', tipo: 'checkbox', rotulo: 'Li e aceito os Termos de Uso, a Política de Privacidade (LGPD) e o Termo de Confidencialidade.', obrigatorio: true }),
    h('div', { class: 'acoes' }, botao('Cadastrar e receber código', { id: 'botao-cadastrar', tipo: 'submit' })));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        const desafio = await api('/auth/cadastro', { metodo: 'POST', corpo: dadosFormulario(form) });
        etapa.replaceChildren(h('h2', {}, 'Confirme seu e-mail'), formularioOTP(desafio, { finalidade: 'login', aoConcluir: entrar }));
        etapa.querySelector('input').focus();
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  etapa.append(form);
  alvo.append(h('div', { class: 'cartao cartao-estreito' }, h('h1', {}, 'Cadastrar escritório de contabilidade'), etapa,
    h('p', {}, 'Já tem conta? ', h('a', { href: '#/login', id: 'link-login' }, 'Entrar'))));
}

export function recuperar(alvo) {
  const etapa = h('div', {});
  const form = h('form', { id: 'form-recuperar', novalidate: true },
    campo({ id: 'recuperar-email', nome: 'email', rotulo: 'E-mail cadastrado', tipo: 'email', obrigatorio: true, autocomplete: 'email' }),
    h('div', { class: 'acoes' }, botao('Enviar código', { id: 'botao-enviar-codigo', tipo: 'submit' })));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        const desafio = await api('/auth/senha/recuperar', { metodo: 'POST', corpo: dadosFormulario(form) });
        etapa.replaceChildren(formularioOTP(desafio, {
          finalidade: 'recuperacao',
          aoConcluir: async (d) => {
            const r = await api('/auth/senha/redefinir', { metodo: 'POST', corpo: d });
            notificar(r.mensagem);
            location.hash = '#/login';
          },
        }));
        etapa.querySelector('input').focus();
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  etapa.append(form);
  alvo.append(h('div', { class: 'cartao cartao-estreito' }, h('h1', {}, 'Recuperar senha'),
    h('p', {}, 'Enviaremos um código de verificação para redefinir sua senha.'), etapa,
    h('p', {}, h('a', { href: '#/login', id: 'link-voltar-login' }, 'Voltar para o login'))));
}

export function minhaConta(alvo) {
  const u = sessao.usuario;
  const form = h('form', { id: 'form-alterar-senha', novalidate: true },
    campo({ id: 'senha-atual', nome: 'senha_atual', rotulo: 'Senha atual', tipo: 'password', obrigatorio: true, autocomplete: 'current-password' }),
    campo({ id: 'senha-nova', nome: 'nova_senha', rotulo: 'Nova senha', tipo: 'password', obrigatorio: true, autocomplete: 'new-password', dica: REGRA_SENHA }),
    h('div', { class: 'acoes' }, botao('Alterar senha', { id: 'botao-alterar-senha', tipo: 'submit' })));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    await comCarregamento(form.querySelector('[type=submit]'), async () => {
      try {
        const r = await api('/auth/senha/alterar', { metodo: 'POST', corpo: dadosFormulario(form) });
        notificar(r.mensagem);
        sessao.limpar();
        location.hash = '#/login';
      } catch (erro) { mostrarErros(form, erro); }
    });
  });
  alvo.append(h('h1', {}, 'Minha conta'),
    h('section', { class: 'cartao', 'aria-labelledby': 'titulo-dados-conta' }, h('h2', { id: 'titulo-dados-conta' }, 'Dados de acesso'),
      h('dl', {}, h('dt', {}, 'Nome'), h('dd', {}, u.nome), h('dt', {}, 'E-mail'), h('dd', {}, u.email), h('dt', {}, 'Perfil'), h('dd', {}, u.papel))),
    h('section', { class: 'cartao', 'aria-labelledby': 'titulo-alterar-senha' }, h('h2', { id: 'titulo-alterar-senha' }, 'Alterar senha'),
      h('p', { class: 'texto-suave' }, 'Ao alterar a senha, todas as sessões abertas serão encerradas.'), form));
}
