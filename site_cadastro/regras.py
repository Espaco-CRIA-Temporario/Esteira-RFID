"""Regras do armazem: o que cada leitura de tag significa.

FLUXO DE UM PRODUTO
  1. Site ................ cadastra a TV (UID da tag + tipo)            -> CADASTRADO
  2. Sensor da doca de entrada ......................................... -> NA_DOCA
  3. Sensor do inicio da esteira: identifica o tipo e manda o produto
     para a rua certa (comando RUA:n) ................................. -> NA_RUA
     (dentro da rua o trabalho e manual: so se controla a rua)
  4. Site ................ define o destino final (so depois da rua)    -> DESTINO_DEFINIDO
  5. Sensor do fim da esteira: le o destino e manda o produto para a
     doca de saida certa (comando DOCA:n) ............................. -> NA_ESTEIRA
  6. Sensor da doca de saida: confirma que saiu do armazem ............ -> EXPEDIDO
"""
from collections import namedtuple

from banco import normalizar_uid, sensor_ativo

# ============================================================================
#  AJUSTES FACEIS (mude so aqui)
# ============================================================================

# Texto que a ponte envia para o Arduino da esteira. {n} = numero da rua / da doca
# (os numeros ficam nas tabelas "ruas" e "docas", aba Cadastros do site).
COMANDO_RUA = "RUA:{n}"
COMANDO_DOCA = "DOCA:{n}"

# Etapas do produto, na ordem do fluxo: codigo -> nome mostrado no site
STATUS = {
    "CADASTRADO": "Cadastrado",
    "NA_DOCA": "Na doca de entrada",
    "NA_RUA": "Na rua",
    "DESTINO_DEFINIDO": "Destino definido",
    "NA_ESTEIRA": "Na esteira (saindo)",
    "EXPEDIDO": "Expedido",
}

# O que cada sensor significa (o campo "local" da tabela sensores)
LOCAIS_SENSOR = {
    "DOCA_ENTRADA": "Doca de entrada",
    "ESTEIRA_INICIO": "Inicio da esteira",
    "ESTEIRA_FIM": "Fim da esteira",
    "DOCA_SAIDA": "Doca de saida",
}

# Em quais etapas ainda e permitido definir/trocar o destino no site
PODE_DEFINIR_DESTINO = ("NA_RUA", "DESTINO_DEFINIDO")

# Valor especial do "sensor ativo": o leitor so captura o UID para preencher o cadastro
MODO_CADASTRO = "CADASTRO"

# ============================================================================

Resultado = namedtuple("Resultado", "ok mensagem comando")


def rotulo_status(codigo):
    return STATUS.get(codigo, codigo)


def _recusar(mensagem):
    return Resultado(False, mensagem, None)


def _mudar(db, produto_id, status, **campos):
    """Muda o status do produto (e outras colunas, ex.: rua_id=3). Nomes de colunas vem do codigo."""
    sets, valores = ["status=?", "atualizado_em=datetime('now','localtime')"], [status]
    for coluna, valor in campos.items():
        sets.append(f"{coluna}=?")
        valores.append(valor)
    db.execute(f"UPDATE produtos SET {', '.join(sets)} WHERE id=?", valores + [produto_id])


# ---------------------------------------------------------------- site
def cadastrar_produto(db, uid, tipo_id):
    uid = normalizar_uid(uid)
    if not uid:
        return _recusar("Informe o UID da tag.")
    if not db.execute("SELECT 1 FROM tipos_produto WHERE id=?", (tipo_id,)).fetchone():
        return _recusar("Tipo de produto invalido.")
    if db.execute("SELECT 1 FROM produtos WHERE tag_uid=?", (uid,)).fetchone():
        return _recusar(f"O UID {uid} ja esta cadastrado.")
    db.execute("INSERT INTO produtos(tag_uid, tipo_produto_id) VALUES (?,?)", (uid, tipo_id))
    db.commit()
    return Resultado(True, f"Produto {uid} cadastrado.", None)


def definir_destino(db, produto_id, destino_id):
    """Regra: o destino so pode ser definido depois que o produto chegou na rua."""
    p = db.execute("SELECT * FROM produtos WHERE id=?", (produto_id,)).fetchone()
    if not p:
        return _recusar("Produto nao encontrado.")
    if p["status"] not in PODE_DEFINIR_DESTINO:
        return _recusar("O destino so pode ser definido depois que o produto chegar na rua "
                        f"(situacao atual: {rotulo_status(p['status'])}).")
    if not db.execute("SELECT 1 FROM destinos WHERE id=?", (destino_id,)).fetchone():
        return _recusar("Destino invalido.")
    _mudar(db, produto_id, "DESTINO_DEFINIDO", destino_id=destino_id)
    db.commit()
    return Resultado(True, "Destino definido.", None)


# ---------------------------------------------------------------- sensores
# Cada funcao trata a leitura de um tipo de sensor e devolve um Resultado.
def _doca_entrada(db, produto, sensor):
    if produto["status"] != "CADASTRADO":
        return _recusar(f"O produto ja passou da doca de entrada ({rotulo_status(produto['status'])}).")
    _mudar(db, produto["id"], "NA_DOCA", doca_entrada_id=sensor["doca_id"])
    return Resultado(True, "Entrou na doca. Proximo passo: inicio da esteira.", None)


def _esteira_inicio(db, produto, sensor):
    if produto["status"] != "NA_DOCA":
        return _recusar(f"O produto nao esta aguardando a esteira ({rotulo_status(produto['status'])}).")
    rua = db.execute("SELECT * FROM ruas WHERE tipo_produto_id=?", (produto["tipo_produto_id"],)).fetchone()
    if not rua:
        return _recusar("Nao ha rua cadastrada para esse tipo de produto.")
    _mudar(db, produto["id"], "NA_RUA", rua_id=rua["id"])
    return Resultado(True, f"Tipo identificado: desviar para a {rua['codigo']}.", COMANDO_RUA.format(n=rua["numero"]))


def _esteira_fim(db, produto, sensor):
    if produto["status"] == "NA_RUA":
        return _recusar("Produto sem destino definido: defina o destino no site.")
    if produto["status"] != "DESTINO_DEFINIDO":
        return _recusar(f"O produto nao esta pronto para sair ({rotulo_status(produto['status'])}).")
    d = db.execute("""SELECT d.nome, c.codigo, c.numero FROM destinos d
                      LEFT JOIN docas c ON c.id = d.doca_id WHERE d.id=?""", (produto["destino_id"],)).fetchone()
    if d["numero"] is None:
        return _recusar(f"O {d['nome']} nao tem doca de saida cadastrada.")
    _mudar(db, produto["id"], "NA_ESTEIRA")
    return Resultado(True, f"Destino: {d['nome']}. Desviar para a {d['codigo']}.", COMANDO_DOCA.format(n=d["numero"]))


def _doca_saida(db, produto, sensor):
    if produto["status"] != "NA_ESTEIRA":
        return _recusar(f"O produto nao esta saindo pela esteira ({rotulo_status(produto['status'])}).")
    d = db.execute("SELECT nome, doca_id FROM destinos WHERE id=?", (produto["destino_id"],)).fetchone()
    if sensor["doca_id"] and sensor["doca_id"] != d["doca_id"]:
        return _recusar(f"DOCA ERRADA: a doca desse sensor nao e a do {d['nome']}.")
    _mudar(db, produto["id"], "EXPEDIDO")
    return Resultado(True, f"Saiu do armazem para o {d['nome']}.", None)


TRATADORES = {
    "DOCA_ENTRADA": _doca_entrada,
    "ESTEIRA_INICIO": _esteira_inicio,
    "ESTEIRA_FIM": _esteira_fim,
    "DOCA_SAIDA": _doca_saida,
}


def processar_leitura(db, uid, sensor_codigo):
    """Uma tag foi lida por um sensor. Aplica a regra e grava o evento no historico."""
    uid = normalizar_uid(uid)
    sensor = db.execute("SELECT * FROM sensores WHERE codigo=?", (sensor_codigo,)).fetchone()
    produto = db.execute("SELECT * FROM produtos WHERE tag_uid=?", (uid,)).fetchone()

    if not sensor:
        r = _recusar(f"Sensor desconhecido: {sensor_codigo}.")
    elif not produto:
        r = _recusar("Tag nao cadastrada.")
    else:
        r = TRATADORES[sensor["local"]](db, produto, sensor)

    db.execute(
        "INSERT INTO eventos(tag_uid, produto_id, sensor_id, sucesso, resultado, comando) VALUES (?,?,?,?,?,?)",
        (uid, produto["id"] if produto else None, sensor["id"] if sensor else None,
         int(r.ok), r.mensagem, r.comando),
    )
    db.commit()
    return r


def tag_lida(db, uid, sensor=None):
    """Entrada unica para o leitor fisico (usada pela ponte).
    Sem 'sensor', vale o sensor ativo escolhido no site (CADASTRO ou um sensor da operacao)."""
    uid = normalizar_uid(uid)
    alvo = sensor or sensor_ativo(db)
    if alvo != MODO_CADASTRO:
        return processar_leitura(db, uid, alvo)
    if db.execute("SELECT 1 FROM produtos WHERE tag_uid=?", (uid,)).fetchone():
        return _recusar(f"O UID {uid} ja esta cadastrado.")
    db.execute(
        """INSERT INTO ultima_leitura(id, seq, tag_uid) VALUES (1, 1, ?)
           ON CONFLICT(id) DO UPDATE SET seq = seq + 1, tag_uid = excluded.tag_uid,
                                         data_hora = datetime('now','localtime')""", (uid,))
    db.commit()
    return Resultado(True, f"UID {uid} capturado para cadastro.", None)
