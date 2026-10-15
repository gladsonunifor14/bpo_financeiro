// Cliente HTTP da API. O access token fica apenas em memória (não em localStorage,
// para reduzir o impacto de XSS); o refresh token é um cookie HttpOnly gerenciado pelo backend.
const BASE = '/api/v1';
let accessToken = null;
let usuario = null;
let renovando = null;
const ouvintesSessao = new Set();

export class ErroApi extends Error {
  constructor(status, detail) {
    const campos = {};
    let mensagem = 'Não foi possível concluir a operação.';
    if (typeof detail === 'string') {
      mensagem = detail;
    } else if (Array.isArray(detail)) {
      for (const d of detail) {
        const nome = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
        const msg = traduzir(d.msg || '');
        if (nome && typeof nome === 'string') campos[nome] = msg;
      }
      mensagem = Object.keys(campos).length ? 'Corrija os campos indicados.' : traduzir(detail[0]?.msg || mensagem);
    }
    super(mensagem);
    this.status = status;
    this.campos = campos;
  }
}

function traduzir(msg) {
  return msg
    .replace(/^Value error, /, '')
    .replace('Field required', 'Campo obrigatório')
    .replace('value is not a valid email address', 'E-mail inválido')
    .replace(/String should have at least (\d+) characters?/, 'Informe ao menos $1 caracteres')
    .replace(/String should match pattern .*/, 'Formato inválido')
    .replace(/Input should be greater than (\S+)/, 'Informe um valor maior que $1')
    .replace(/Input should be a valid (date|number|integer).*/, 'Valor inválido');
}

export const sessao = {
  get usuario() { return usuario; },
  get autenticado() { return !!accessToken; },
  definir(token, u) { accessToken = token; usuario = u; ouvintesSessao.forEach((f) => f(u)); },
  limpar() { accessToken = null; usuario = null; ouvintesSessao.forEach((f) => f(null)); },
  aoMudar(f) { ouvintesSessao.add(f); },
};

async function renovar() {
  if (!renovando) {
    renovando = fetch(`${BASE}/auth/refresh`, {
      method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' },
    }).then(async (r) => {
      if (!r.ok) { sessao.limpar(); return false; }
      const dados = await r.json();
      sessao.definir(dados.access_token, dados.usuario);
      return true;
    }).catch(() => false).finally(() => { setTimeout(() => { renovando = null; }, 0); });
  }
  return renovando;
}

export async function restaurarSessao() {
  return renovar();
}

export async function api(caminho, { metodo = 'GET', corpo, formulario, bruto = false, tentarRenovar = true } = {}) {
  const headers = { 'X-Requested-With': 'fetch' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let body;
  if (formulario) body = formulario;
  else if (corpo !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(corpo); }
  let resp;
  try {
    resp = await fetch(BASE + caminho, { method: metodo, headers, body, credentials: 'same-origin' });
  } catch {
    throw new ErroApi(0, 'Sem conexão com o servidor. Verifique sua internet e tente novamente.');
  }
  if (resp.status === 401 && tentarRenovar && !caminho.startsWith('/auth/')) {
    if (await renovar()) return api(caminho, { metodo, corpo, formulario, bruto, tentarRenovar: false });
    window.dispatchEvent(new CustomEvent('sessao-expirada'));
  }
  if (!resp.ok) {
    let detail;
    try { detail = (await resp.json()).detail; } catch { detail = undefined; }
    if (resp.status === 429 && !detail) detail = 'Muitas tentativas. Aguarde um minuto.';
    if (resp.status >= 500) detail = 'Erro no servidor. Tente novamente em instantes.';
    throw new ErroApi(resp.status, detail);
  }
  if (bruto) return resp;
  if (resp.status === 204) return null;
  return resp.json();
}

// Download de arquivos (CSV, XML, PDF) mantendo a autenticação por cabeçalho
export async function baixar(caminho, nomeArquivo) {
  const resp = await api(caminho, { bruto: true });
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nomeArquivo;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
