"""Testes ponta a ponta no navegador (Playwright + Chromium).

Percorre o fluxo real: cadastro do escritório com OTP, cliente via CNPJ, importação de
XML e OFX, classificação, relatórios — e verifica regras de acessibilidade em cada tela
(rótulos, nomes acessíveis, ids únicos, foco visível, ausência de rolagem horizontal no mobile).
Pulado automaticamente se o Playwright/Chromium não estiver disponível.
"""
import os
import re
import socket
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")

from .conftest import CNPJ_CLIENTE, CNPJ_COMPRADOR, CNPJ_ESCRITORIO, CNPJ_FORNECEDOR, SENHA  # noqa: E402
from .util import OFX, xml_nfe  # noqa: E402

AUDITORIA_A11Y = """
() => {
  const problemas = [];
  const visivel = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const ids = {};
  document.querySelectorAll('[id]').forEach((el) => { ids[el.id] = (ids[el.id] || 0) + 1; });
  Object.entries(ids).filter(([, n]) => n > 1).forEach(([id]) => problemas.push('id duplicado: ' + id));
  document.querySelectorAll('input, select, textarea').forEach((el) => {
    if (el.type === 'hidden') return;
    const temRotulo = (el.id && document.querySelector(`label[for="${el.id}"]`)) || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby');
    if (!temRotulo) problemas.push('campo sem rótulo: ' + (el.id || el.name || el.outerHTML.slice(0, 60)));
    if (!el.id) problemas.push('campo sem id: ' + (el.name || el.outerHTML.slice(0, 60)));
  });
  document.querySelectorAll('button, a[href]').forEach((el) => {
    if (!visivel(el)) return;
    const nome = (el.getAttribute('aria-label') || el.textContent || '').trim();
    if (!nome) problemas.push('controle sem nome acessível: ' + el.outerHTML.slice(0, 80));
  });
  document.querySelectorAll('button').forEach((el) => {
    if (visivel(el) && !el.id && !el.closest('dialog')) problemas.push('botão sem id: ' + el.textContent.trim().slice(0, 40));
  });
  document.querySelectorAll('img, svg[role="img"]').forEach((el) => {
    if (el.tagName === 'IMG' && !el.hasAttribute('alt')) problemas.push('imagem sem alt');
    if (el.tagName.toLowerCase() === 'svg' && !el.getAttribute('aria-labelledby') && !el.getAttribute('aria-label')) problemas.push('gráfico sem descrição');
  });
  if (document.querySelectorAll('h1').length !== 1) problemas.push('página deve ter exatamente um h1 (tem ' + document.querySelectorAll('h1').length + ')');
  return problemas;
}
"""


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servidor(tmp_path):
    import uvicorn

    from app.database import Base, SessionLocal, _criar_engine, engine
    from app.main import app

    # O navegador faz requisições concorrentes: usa SQLite em arquivo (o de memória é single-connection)
    eng = _criar_engine(f"sqlite:///{tmp_path / 'e2e.db'}")
    Base.metadata.create_all(eng)
    SessionLocal.configure(bind=eng)

    porta = _porta_livre()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{porta}"
    srv.should_exit = True
    t.join(timeout=5)
    SessionLocal.configure(bind=engine)
    eng.dispose()


@pytest.fixture
def navegador():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except Exception as e:  # pragma: no cover
            pytest.skip(f"Chromium indisponível: {e}")
        yield b
        b.close()


def _sem_problemas(page, contexto):
    problemas = page.evaluate(AUDITORIA_A11Y)
    assert not problemas, f"[{contexto}] " + "; ".join(problemas)


def _foto(page, nome):
    """Screenshots para revisão visual/QA quando E2E_SCREENSHOTS aponta para uma pasta."""
    pasta = os.environ.get("E2E_SCREENSHOTS")
    if pasta:
        page.wait_for_timeout(150)
        page.screenshot(path=os.path.join(pasta, f"{nome}.png"), full_page=True)


def _codigo(caixa) -> str:
    return re.search(r"\b(\d{6})\b", caixa[-1]["corpo"]).group(1)


def test_fluxo_completo_e_acessibilidade(servidor, navegador, caixa, tmp_path):
    erros_console = []
    page = navegador.new_page()
    page.on("console", lambda m: erros_console.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: erros_console.append(str(e)))

    # ---- cadastro com OTP
    page.goto(servidor + "/#/cadastro")
    page.wait_for_selector("h1:has-text('Cadastrar escritório')")
    _sem_problemas(page, "cadastro")
    page.click("#botao-cadastrar")  # vazio: erros associados aos campos
    page.wait_for_selector(".resumo-erros")
    _foto(page, "01-cadastro-erros")
    assert page.get_attribute("#cadastro-cnpj", "aria-invalid") == "true"
    assert "cadastro-cnpj-erro" in page.get_attribute("#cadastro-cnpj", "aria-describedby")
    page.fill("#cadastro-cnpj", CNPJ_ESCRITORIO)
    page.fill("#cadastro-crc", "CE-012345/O")
    page.fill("#cadastro-nome", "Ana Contadora")
    page.fill("#cadastro-email", "ana@contabil.com")
    page.fill("#cadastro-senha", SENHA)
    page.check("#cadastro-aceite")
    page.click("#botao-cadastrar")
    page.wait_for_selector("#otp-codigo-login")
    page.fill("#otp-codigo-login", _codigo(caixa))
    page.click("#botao-verificar-login")

    # ---- painel vazio com CTA
    page.wait_for_selector("h1:has-text('Painel do escritório')")
    assert page.is_visible("#painel-cta-primeiro-cliente")
    _foto(page, "02-painel-vazio")
    _sem_problemas(page, "painel vazio")
    page.click("#painel-cta-primeiro-cliente")

    # ---- cliente pelo CNPJ (Receita simulada)
    page.wait_for_selector("#cliente-cnpj")
    page.fill("#cliente-cnpj", CNPJ_CLIENTE)
    page.click("#botao-buscar-receita")
    page.wait_for_selector("#previa-receita .aviso-sucesso")
    assert page.input_value("#cliente-razao") == "COMERCIO MODELO LTDA"
    page.click("#botao-salvar-cliente")
    page.wait_for_selector("#cliente-aba-painel")

    # ---- Painel BI vazio: operações impossíveis com CTA
    assert page.is_visible("#cta-bi-notas")
    _foto(page, "03-cliente-sem-dados")
    _sem_problemas(page, "cliente sem dados")
    page.click("#cliente-aba-relatorios")
    assert page.is_disabled("#botao-gerar-dre")
    assert page.get_attribute("#botao-gerar-dre", "aria-describedby") == "pre-dre"

    # ---- extratos: importação desabilitada até cadastrar conta
    page.click("#cliente-aba-extratos")
    page.wait_for_selector("#botao-importar-extrato")
    assert page.is_disabled("#botao-importar-extrato")
    page.click("#cta-cadastrar-conta")
    page.fill("#conta-banco-nome-corrente", "Banco do Brasil")
    page.click("#botao-salvar-conta-corrente")
    page.wait_for_selector("#botao-importar-extrato:not([disabled])")
    ofx = tmp_path / "marco.ofx"
    ofx.write_bytes(OFX)
    page.set_input_files("#extrato-arquivo", str(ofx))
    page.click("#botao-importar-extrato")
    page.wait_for_selector("text=4 lançamento(s) importado(s)")
    page.wait_for_selector("#tabela-lancamentos")
    _foto(page, "04-extratos")
    _sem_problemas(page, "extratos")
    # classifica a tarifa pelo select rotulado
    sel = page.locator("select[id^='lanc-conta-']").first
    sel.select_option(label="4.3.01 — Tarifas bancárias")
    page.wait_for_selector("text=Lançamento classificado")

    # ---- notas fiscais
    page.goto(servidor + "/#/clientes/1/notas")
    page.wait_for_selector("#notas-arquivos")
    venda = tmp_path / "venda.xml"
    venda.write_bytes(xml_nfe(CNPJ_CLIENTE, CNPJ_COMPRADOR, [("Notebook", "5102", 10000.0)], numero=1, icms=1800))
    compra = tmp_path / "compra.xml"
    compra.write_bytes(xml_nfe(CNPJ_FORNECEDOR, CNPJ_CLIENTE, [("Notebook", "6102", 6000.0)], numero=2))
    page.set_input_files("#notas-arquivos", [str(venda), str(compra)])
    page.click("#botao-importar-notas")
    page.wait_for_selector("text=2 importada(s)")
    page.wait_for_selector("#tabela-notas")
    _sem_problemas(page, "notas")
    page.click("#ver-nota-1")
    page.wait_for_selector("dialog[open]")
    page.keyboard.press("Escape")

    # ---- relatórios: DRE com cabeçalho do escritório
    page.goto(servidor + "/#/clientes/1/relatorios")
    page.wait_for_selector("#botao-gerar-dre:not([disabled])")
    page.fill("#relatorio-inicio", "2026-03-01")
    page.fill("#relatorio-fim", "2026-03-31")
    page.click("#botao-gerar-dre")
    page.wait_for_selector("#tabela-dre")
    assert "CONTABIL EXEMPLO LTDA" in page.inner_text(".cabecalho-relatorio")
    assert "CRC CE-012345/O" in page.inner_text(".cabecalho-relatorio")
    _foto(page, "05-dre")
    _sem_problemas(page, "dre")

    # ---- Painel BI com gráfico acessível
    page.goto(servidor + "/#/clientes/1/painel")
    page.fill("#bi-inicio", "2026-01-01")
    page.click("#botao-atualizar-bi")
    page.wait_for_selector("svg#grafico-resultado")
    _foto(page, "06-painel-bi")
    _sem_problemas(page, "painel bi")

    # ---- navegação por teclado nas abas e foco visível
    page.focus("#cliente-aba-painel")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.id") == "cliente-aba-notas"
    outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    assert outline != "none"

    # ---- mobile: cartões e sem rolagem horizontal da página
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(servidor + "/#/clientes/1/notas")
    page.reload()
    page.wait_for_selector("#cliente-painel-notas .lista-cartoes")
    assert not page.is_visible("#tabela-notas")
    assert page.is_visible("#botao-importar-notas")  # ação essencial visível (barra fixa)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert page.is_visible("#botao-menu")
    _foto(page, "07-mobile-notas")
    page.click("#botao-menu")
    assert page.get_attribute("#botao-menu", "aria-expanded") == "true"

    # ---- auditoria registrou as ações
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(servidor + "/#/auditoria")
    page.wait_for_selector("#tabela-auditoria")
    assert "ana@contabil.com" in page.inner_text("#tabela-auditoria")
    _sem_problemas(page, "auditoria")

    assert not [e for e in erros_console if "Content Security Policy" in e or "Uncaught" in e], erros_console
