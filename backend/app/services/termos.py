"""Termos LGPD padrão publicados para cada novo escritório."""
from sqlalchemy.orm import Session

from ..models import TermoVersao
from .contratos import sha256

TERMOS_PADRAO = [
    (
        "termos_uso",
        "Termos de Uso da Plataforma",
        "1. A plataforma destina-se à gestão financeira terceirizada (BPO) entre o escritório contábil e seus clientes.\n"
        "2. O usuário é responsável pela guarda de suas credenciais; o acesso exige senha e código de verificação (OTP) enviado por e-mail.\n"
        "3. Todas as operações são registradas em trilha de auditoria (quem, quando e o que foi alterado).\n"
        "4. É vedado o uso da plataforma para fins ilícitos ou o envio de documentos de terceiros sem autorização.",
    ),
    (
        "politica_privacidade",
        "Política de Privacidade (LGPD)",
        "Controlador: o cliente contratante. Operador: o escritório contábil. Dados tratados: dados cadastrais de empresas e de seus "
        "representantes, documentos fiscais, extratos bancários e de aplicações. Finalidade: execução do contrato de BPO Financeiro "
        "e cumprimento de obrigações legais (LGPD art. 7º, II e V). Compartilhamento: apenas com provedores necessários (hospedagem, "
        "e-mail, consulta de CNPJ, Open Finance mediante consentimento). Retenção: pelo prazo contratual e pelos prazos legais de guarda "
        "fiscal (5 anos, CTN art. 173/174). Direitos do titular (art. 18): confirmação, acesso, correção, anonimização, portabilidade, "
        "eliminação e revogação do consentimento, exercíveis pelo canal do Encarregado (DPO) indicado pelo escritório. "
        "Segurança: criptografia em trânsito (TLS), senhas com Argon2id, MFA por OTP, controle de acesso por perfil e auditoria.",
    ),
    (
        "confidencialidade",
        "Termo de Confidencialidade",
        "As partes comprometem-se a manter sigilo absoluto sobre informações financeiras, fiscais, bancárias, estratégicas e pessoais "
        "a que tiverem acesso, utilizando-as exclusivamente para a execução dos serviços contratados, durante a vigência e por 5 anos após o "
        "término da relação, ressalvadas requisições legais de autoridades competentes. O descumprimento sujeita o infrator a perdas e danos.",
    ),
]


def publicar_padrao(db: Session, escritorio_id: int) -> None:
    for tipo, titulo, conteudo in TERMOS_PADRAO:
        db.add(
            TermoVersao(
                escritorio_id=escritorio_id,
                tipo=tipo,
                versao=1,
                titulo=titulo,
                conteudo=conteudo,
                hash_sha256=sha256(conteudo),
            )
        )
