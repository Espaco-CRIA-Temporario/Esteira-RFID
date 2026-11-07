"""Site e API. As regras ficam em regras.py, o banco em banco.py e o HTML em templates/."""
import sqlite3
from urllib.parse import quote

from flask import Flask, jsonify, redirect, render_template, request

import banco
from banco import get_db, leitor_ativo, normalizar_uid
from regras import ESTEIRA_ACIONA_EM, ESTEIRA_INICIO, definir_destino, processar_leitura

app = Flask(__name__)
banco.init_app(app)


# ---------------------------------------------------------------- API (leitores / esteira)
@app.post("/api/leituras")
def api_leitura():
    """O leitor (ESP32 / script ponte) envia: {"uid": "04A1B2C3", "leitor": "LEITOR-PP-TV45-A"}"""
    d = request.get_json(silent=True) or {}
    ok, msg = processar_leitura(get_db(), d.get("uid"), d.get("leitor"))
    return jsonify(ok=ok, mensagem=msg), (200 if ok else 422)


@app.post("/api/tag-lida")
def api_tag_lida():
    """Endpoint unico usado pela ponte USB: {"uid": "04A1B2C3"}  (opcional: "leitor": "LEITOR-...").
    Sem "leitor", vale o leitor ativo escolhido no site (CADASTRO ou um leitor da operacao).
    Resposta: ok, mensagem e, quando a esteira deve andar, esteira=true e rota."""
    d = request.get_json(silent=True) or {}
    db = get_db()
    uid = normalizar_uid(d.get("uid"))
    if not uid:
        return jsonify(ok=False, mensagem="UID vazio.", esteira=False, rota=None), 400

    alvo = d.get("leitor") or leitor_ativo(db)

    if alvo == "CADASTRO":
        if db.execute("SELECT 1 FROM produtos WHERE tag_uid=?", (uid,)).fetchone():
            return jsonify(ok=False, mensagem=f"UID {uid} ja esta cadastrado.", esteira=False, rota=None), 422
        db.execute(
            """INSERT INTO ultima_leitura(id, seq, tag_uid) VALUES (1, 1, ?)
               ON CONFLICT(id) DO UPDATE SET seq = seq + 1, tag_uid = excluded.tag_uid,
                                             data_hora = datetime('now','localtime')""",
            (uid,),
        )
        db.commit()
        return jsonify(ok=True, mensagem=f"UID {uid} capturado para cadastro.", esteira=False, rota=None)

    ok, msg = processar_leitura(db, uid, alvo)
    esteira, rota = False, None
    leitor = db.execute("SELECT local FROM leitores WHERE codigo=?", (alvo,)).fetchone()
    # A esteira anda quando um produto passa com sucesso pela doca de saida.
    if ok and (alvo == ESTEIRA_INICIO or (leitor and leitor["local"] == ESTEIRA_ACIONA_EM)):
        esteira = True
        r = db.execute(
            """SELECT d.rota_esteira FROM produtos p JOIN destinos d ON d.id = p.destino_id
               WHERE p.tag_uid=?""", (uid,)).fetchone()
        rota = r["rota_esteira"] if r else None
    return jsonify(ok=ok, mensagem=msg, esteira=esteira, rota=rota), (200 if ok else 422)


@app.get("/api/ultima-leitura")
def api_ultima_leitura():
    r = get_db().execute("SELECT seq, tag_uid, data_hora FROM ultima_leitura WHERE id=1").fetchone()
    return jsonify(seq=r["seq"], uid=r["tag_uid"], data_hora=r["data_hora"]) if r else jsonify(seq=0, uid="", data_hora="")


@app.get("/api/produtos/<uid>/destino")
def api_destino(uid):
    """A esteira consulta: qual rota esse produto deve seguir?"""
    r = get_db().execute(
        """SELECT p.status, d.nome, d.rota_esteira FROM produtos p
           LEFT JOIN destinos d ON d.id = p.destino_id WHERE p.tag_uid=?""",
        (uid.strip().upper(),),
    ).fetchone()
    if not r:
        return jsonify(ok=False, mensagem="Tag nao cadastrada."), 404
    if r["rota_esteira"] is None:
        return jsonify(ok=False, mensagem="Produto sem destino definido.", status=r["status"]), 409
    return jsonify(ok=True, destino=r["nome"], rota=r["rota_esteira"], status=r["status"])


@app.get("/api/produtos")
def api_produtos():
    rows = get_db().execute("SELECT * FROM produtos").fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------- site (sem CSS)
@app.get("/")
def index():
    db = get_db()
    q = lambda sql: db.execute(sql).fetchall()
    return render_template(
        "index.html",
        msg=request.args.get("msg"),
        ativo=leitor_ativo(db),
        ultima=db.execute("SELECT * FROM ultima_leitura WHERE id=1").fetchone(),
        tipos=q("SELECT * FROM tipos_produto ORDER BY polegadas"),
        destinos=q("SELECT * FROM destinos ORDER BY id"),
        leitores=q("SELECT * FROM leitores ORDER BY local, id"),
        produtos=q("""SELECT p.id, p.tag_uid, p.status, t.descricao AS tipo, pp.codigo AS palet, d.nome AS destino
                      FROM produtos p JOIN tipos_produto t ON t.id=p.tipo_id
                      LEFT JOIN porta_palets pp ON pp.id=p.palet_id
                      LEFT JOIN destinos d ON d.id=p.destino_id ORDER BY p.id"""),
        palets=q("""SELECT pp.codigo, t.descricao AS tipo,
                    (SELECT COUNT(*) FROM produtos p WHERE p.palet_id=pp.id AND p.status IN ('NO_PALET','DESTINO_DEFINIDO')) AS qtd
                    FROM porta_palets pp JOIN tipos_produto t ON t.id=pp.tipo_produto_id ORDER BY pp.id"""),
        docas=q("""SELECT dc.codigo, dc.tipo, d.nome AS destino FROM docas dc
                   LEFT JOIN destinos d ON d.id=dc.destino_id ORDER BY dc.id"""),
        eventos=q("""SELECT e.*, l.codigo AS leitor FROM eventos_leitura e
                     LEFT JOIN leitores l ON l.id=e.leitor_id ORDER BY e.id DESC LIMIT 20"""),
    )


def voltar(msg):
    return redirect("/?msg=" + quote(msg))


@app.post("/produtos")
def cadastrar():
    db = get_db()
    uid = request.form["uid"].strip().upper().replace(" ", "")
    try:
        db.execute("INSERT INTO produtos(tag_uid, tipo_id) VALUES (?,?)", (uid, request.form["tipo_id"]))
        db.commit()
        return voltar(f"Produto {uid} cadastrado.")
    except sqlite3.IntegrityError:
        return voltar(f"Erro: UID {uid} ja esta cadastrado.")


@app.post("/produtos/<int:pid>/destino")
def destino(pid):
    ok, msg = definir_destino(get_db(), pid, request.form["destino_id"])
    return voltar(msg)


@app.post("/leitor-ativo")
def trocar_leitor():
    db = get_db()
    alvo = request.form["leitor"]
    if alvo not in ("CADASTRO", ESTEIRA_INICIO) and not db.execute("SELECT 1 FROM leitores WHERE codigo=?", (alvo,)).fetchone():
        return voltar("Leitor invalido.")
    db.execute("UPDATE config SET valor=? WHERE chave='leitor_ativo'", (alvo,))
    db.commit()
    return voltar(f"Leitor fisico agora funciona como: {alvo}")


@app.post("/simular")
def simular():
    ok, msg = processar_leitura(get_db(), request.form["uid"], request.form["leitor"])
    return voltar(("OK: " if ok else "ERRO: ") + msg)


@app.get("/banco")
def ver_banco():
    """Mostra o conteudo de todas as tabelas (so leitura), para conferir o banco pelo navegador."""
    return render_template("banco.html", dados=banco.tabelas(get_db()), arquivo=banco.DB)


banco.init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
