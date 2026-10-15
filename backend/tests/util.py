from datetime import date

from app.services.cnpj import _PESOS_1, _PESOS_2, _dv


def gerar_cnpj(base12: str) -> str:
    d1 = _dv(base12, _PESOS_1)
    d2 = _dv(base12 + str(d1), _PESOS_2)
    return f"{base12}{d1}{d2}"


def xml_nfe(
    emitente: str,
    destinatario: str,
    itens: list[tuple[str, str, float]],
    numero: int = 1,
    emissao: date = date(2026, 3, 10),
    tp_nf: str = "1",
    icms: float = 0,
    pis: float = 0,
    cofins: float = 0,
    duplicatas: list[tuple[str, date, float]] | None = None,
    cstat: str = "100",
    extra: str = "",
) -> bytes:
    """itens: (descricao, cfop, valor)"""
    chave = f"23{emissao:%y%m}{emitente}55001{numero:09d}1{numero:08d}"
    chave = chave + str(sum(int(c) for c in chave) % 10)
    total = sum(v for _, _, v in itens)
    dets = "".join(
        f'<det nItem="{i}"><prod><cProd>P{i}</cProd><xProd>{d}</xProd><NCM>84713012</NCM><CFOP>{c}</CFOP>'
        f"<qCom>1.0000</qCom><vUnCom>{v:.2f}</vUnCom><vProd>{v:.2f}</vProd></prod></det>"
        for i, (d, c, v) in enumerate(itens, start=1)
    )
    dups = ""
    if duplicatas:
        dups = "<cobr>" + "".join(f"<dup><nDup>{n}</nDup><dVenc>{dv.isoformat()}</dVenc><vDup>{vv:.2f}</vDup></dup>" for n, dv, vv in duplicatas) + "</cobr>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">{extra}
<NFe><infNFe Id="NFe{chave}" versao="4.00">
<ide><natOp>VENDA</natOp><mod>55</mod><serie>1</serie><nNF>{numero}</nNF><dhEmi>{emissao.isoformat()}T10:00:00-03:00</dhEmi><tpNF>{tp_nf}</tpNF></ide>
<emit><CNPJ>{emitente}</CNPJ><xNome>EMITENTE {emitente[:4]}</xNome></emit>
<dest><CNPJ>{destinatario}</CNPJ><xNome>DESTINATARIO {destinatario[:4]}</xNome></dest>
{dets}
<total><ICMSTot><vProd>{total:.2f}</vProd><vDesc>0.00</vDesc><vFrete>0.00</vFrete><vICMS>{icms:.2f}</vICMS><vST>0.00</vST><vIPI>0.00</vIPI><vPIS>{pis:.2f}</vPIS><vCOFINS>{cofins:.2f}</vCOFINS><vNF>{total:.2f}</vNF></ICMSTot></total>
{dups}
</infNFe></NFe>
<protNFe><infProt><cStat>{cstat}</cStat></infProt></protNFe>
</nfeProc>""".encode()


OFX = b"""OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260305<TRNAMT>-49.90<FITID>A1<MEMO>TARIFA PACOTE SERVICOS 03/26
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260306<TRNAMT>-3500.00<FITID>A2<MEMO>PIX ENVIADO IMOBILIARIA CENTRO 123456
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260310<TRNAMT>12000.00<FITID>A3<MEMO>PIX RECEBIDO CLIENTE ALFA 998877
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260315<TRNAMT>-890.45<FITID>A4<MEMO>PAGTO ENERGIA ENEL 0315
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

OFX_ABRIL = b"""OFXHEADER:100
<OFX><BANKTRANLIST>
<STMTTRN><DTPOSTED>20260406<TRNAMT>-3500.00<FITID>B2<MEMO>PIX ENVIADO IMOBILIARIA CENTRO 654321
<STMTTRN><DTPOSTED>20260415<TRNAMT>-912.10<FITID>B4<MEMO>PAGTO ENERGIA ENEL 0415
<STMTTRN><DTPOSTED>20260420<TRNAMT>-150.00<FITID>B5<MEMO>COMPRA CARTAO PADARIA SAO JOSE
</BANKTRANLIST></OFX>
"""
