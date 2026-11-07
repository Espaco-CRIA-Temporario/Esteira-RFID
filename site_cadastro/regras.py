"""Regras do armazem: o que cada leitura de tag significa e quando o destino pode ser definido."""

# Em qual tipo de leitor a esteira deve andar (DOCA_ENTRADA, PALET ou DOCA_SAIDA)
ESTEIRA_ACIONA_EM = "DOCA_SAIDA"

# Leitor virtual: o leitor fisico no INICIO da esteira. Nao precisa existir na tabela leitores.
# Produto com destino definido que passa aqui e liberado na esteira para a doca do seu destino.
ESTEIRA_INICIO = "ESTEIRA"

# Quantas docas a esteira fisica atende (3 sensores + 3 servos). Destinos acima disso sao recusados.
ESTEIRA_DOCAS = 3


def definir_destino(db, produto_id, destino_id):
    """Regra: o destino so pode ser definido depois que o produto chegou ao palet."""
    p = db.execute("SELECT * FROM produtos WHERE id=?", (produto_id,)).fetchone()
    if not p:
        return False, "Produto nao encontrado."
    if p["status"] not in ("NO_PALET", "DESTINO_DEFINIDO"):
        return False, f"Destino so pode ser definido apos o produto chegar ao palet (status atual: {p['status']})."
    if not db.execute("SELECT 1 FROM destinos WHERE id=?", (destino_id,)).fetchone():
        return False, "Destino invalido."
    db.execute("UPDATE produtos SET destino_id=?, status='DESTINO_DEFINIDO' WHERE id=?", (destino_id, produto_id))
    db.commit()
    return True, "Destino definido."


def processar_leitura(db, uid, leitor_codigo):
    """Chamado toda vez que um leitor RFID le uma tag. Retorna (ok, mensagem)."""
    uid = (uid or "").strip().upper().replace(" ", "")
    leitor = db.execute("SELECT * FROM leitores WHERE codigo=?", (leitor_codigo,)).fetchone()
    produto = db.execute("SELECT * FROM produtos WHERE tag_uid=?", (uid,)).fetchone()

    def fim(ok, msg):
        db.execute(
            "INSERT INTO eventos_leitura(tag_uid, produto_id, leitor_id, sucesso, resultado) VALUES (?,?,?,?,?)",
            (uid, produto["id"] if produto else None, leitor["id"] if leitor else None, int(ok), msg),
        )
        db.commit()
        return ok, msg

    if leitor_codigo == ESTEIRA_INICIO:
        if not produto:
            return fim(False, "Tag nao cadastrada.")
        if produto["status"] != "DESTINO_DEFINIDO":
            return fim(False, f"Produto sem destino definido / fora de sequencia (status: {produto['status']}).")
        d = db.execute("SELECT nome, rota_esteira FROM destinos WHERE id=?", (produto["destino_id"],)).fetchone()
        if d["rota_esteira"] > ESTEIRA_DOCAS:
            return fim(False, f"A esteira so atende {ESTEIRA_DOCAS} docas; o {d['nome']} nao e atendido por ela.")
        db.execute("UPDATE produtos SET status='ENTREGUE' WHERE id=?", (produto["id"],))
        return fim(True, f"Produto liberado na esteira para o {d['nome']}.")

    if not leitor:
        return fim(False, "Leitor desconhecido.")
    if not produto:
        return fim(False, "Tag nao cadastrada.")

    st = produto["status"]

    if leitor["local"] == "DOCA_ENTRADA":
        if st != "CADASTRADO":
            return fim(False, f"Produto ja passou da doca de entrada (status: {st}).")
        db.execute("UPDATE produtos SET status='NA_DOCA', doca_entrada_id=? WHERE id=?", (leitor["doca_id"], produto["id"]))
        palets = [r["codigo"] for r in db.execute(
            "SELECT codigo FROM porta_palets WHERE tipo_produto_id=?", (produto["tipo_id"],))]
        return fim(True, "Chegou na doca. Palets corretos: " + " ou ".join(palets))

    if leitor["local"] == "PALET":
        if st != "NA_DOCA":
            return fim(False, f"Produto nao esta aguardando palet (status: {st}).")
        palet = db.execute("SELECT * FROM porta_palets WHERE id=?", (leitor["palet_id"],)).fetchone()
        if palet["tipo_produto_id"] != produto["tipo_id"]:
            return fim(False, f"PALET ERRADO: {palet['codigo']} nao e o palet desse tipo de produto.")
        db.execute("UPDATE produtos SET status='NO_PALET', palet_id=? WHERE id=?", (palet["id"], produto["id"]))
        return fim(True, f"Produto confirmado no palet {palet['codigo']}. Ja pode definir o destino.")

    if leitor["local"] == "DOCA_SAIDA":
        if st != "DESTINO_DEFINIDO":
            return fim(False, f"Produto sem destino definido / fora de sequencia (status: {st}).")
        doca = db.execute("SELECT * FROM docas WHERE id=?", (leitor["doca_id"],)).fetchone()
        if doca["destino_id"] != produto["destino_id"]:
            return fim(False, f"DOCA DE SAIDA ERRADA: {doca['codigo']} nao corresponde ao destino cadastrado.")
        db.execute("UPDATE produtos SET status='ENTREGUE' WHERE id=?", (produto["id"],))
        return fim(True, f"Produto entregue pela doca {doca['codigo']}.")

    return fim(False, "Local de leitor invalido.")
