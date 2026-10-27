import os
import sqlite3
from urllib.parse import quote

from flask import Flask, g, jsonify, redirect, render_template_string, request

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("ARMAZEM_DB", os.path.join(BASE, "armazem.db"))

app = Flask(__name__)

# Em qual tipo de leitor a esteira deve andar (DOCA_ENTRADA, PALET ou DOCA_SAIDA)
ESTEIRA_ACIONA_EM = "DOCA_SAIDA"


# ---------------------------------------------------------------- banco
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()


def seed(db):
    for pol in (45, 50, 55, 60):
        db.execute("INSERT INTO tipos_produto(descricao, polegadas) VALUES (?,?)", (f"TV {pol}", pol))
    for n in range(1, 5):
        db.execute("INSERT INTO destinos(nome, rota_esteira) VALUES (?,?)", (f"Destino {n}", n))
    for n in range(1, 5):
        db.execute("INSERT INTO docas(codigo, tipo) VALUES (?, 'ENTRADA')", (f"ENT-{n}",))
    for n in range(1, 5):
        db.execute("INSERT INTO docas(codigo, tipo, destino_id) VALUES (?, 'SAIDA', ?)", (f"SAI-{n}", n))
    for t in db.execute("SELECT id, polegadas FROM tipos_produto").fetchall():
        for letra in ("A", "B"):
            db.execute(
                "INSERT INTO porta_palets(codigo, tipo_produto_id) VALUES (?,?)",
                (f"PP-TV{t['polegadas']}-{letra}", t["id"]),
            )
    for d in db.execute("SELECT id, codigo, tipo FROM docas").fetchall():
        local = "DOCA_ENTRADA" if d["tipo"] == "ENTRADA" else "DOCA_SAIDA"
        db.execute(
            "INSERT INTO leitores(codigo, local, doca_id) VALUES (?,?,?)",
            (f"LEITOR-{d['codigo']}", local, d["id"]),
        )
    for p in db.execute("SELECT id, codigo FROM porta_palets").fetchall():
        db.execute(
            "INSERT INTO leitores(codigo, local, palet_id) VALUES (?, 'PALET', ?)",
            (f"LEITOR-{p['codigo']}", p["id"]),
        )


def init_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    if db.execute("SELECT COUNT(*) FROM tipos_produto").fetchone()[0] == 0:
        seed(db)
    db.commit()
    db.close()


# ---------------------------------------------------------------- regras
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


# ---------------------------------------------------------------- API (leitores / esteira)
@app.post("/api/leituras")
def api_leitura():
    """O leitor (ESP32 / script ponte) envia: {"uid": "04A1B2C3", "leitor": "LEITOR-PP-TV45-A"}"""
    d = request.get_json(silent=True) or {}
    ok, msg = processar_leitura(get_db(), d.get("uid"), d.get("leitor"))
    return jsonify(ok=ok, mensagem=msg), (200 if ok else 422)


def normalizar_uid(uid):
    return (uid or "").strip().upper().replace(" ", "")


def leitor_ativo(db):
    return db.execute("SELECT valor FROM config WHERE chave='leitor_ativo'").fetchone()[0]


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
    if ok and leitor and leitor["local"] == ESTEIRA_ACIONA_EM:
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
PAGINA = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8"><title>Teste - Armazem</title></head><body>
<h1>Armazem - teste do banco de dados</h1>
{% if msg %}<p><b>>> {{ msg }}</b></p>{% endif %}

<h2>0. Leitor fisico (RFID)</h2>
<form method="post" action="/leitor-ativo">
  O leitor esta funcionando como:
  <select name="leitor">
    <option value="CADASTRO" {{ 'selected' if ativo == 'CADASTRO' }}>CADASTRO (so captura o UID)</option>
    {% for l in leitores %}<option value="{{l.codigo}}" {{ 'selected' if ativo == l.codigo }}>{{l.codigo}}</option>{% endfor %}
  </select>
  <button>Trocar</button>
</form>
<p id="aviso-tag">Ultima tag lida no cadastro: <b id="ultima-uid">{{ ultima.tag_uid if ultima else '(nenhuma)' }}</b></p>

<h2>1. Cadastrar produto</h2>
<form method="post" action="/produtos">
  UID da tag: <input id="campo-uid" name="uid" required placeholder="aproxime a tag do leitor ou digite">
  Tipo: <select name="tipo_id">{% for t in tipos %}<option value="{{t.id}}">{{t.descricao}}</option>{% endfor %}</select>
  <button>Cadastrar</button>
</form>

<h2>2. Produtos</h2>
<table border="1" cellpadding="4">
<tr><th>ID</th><th>UID</th><th>Tipo</th><th>Status</th><th>Palet</th><th>Destino</th><th>Definir destino</th></tr>
{% for p in produtos %}
<tr><td>{{p.id}}</td><td>{{p.tag_uid}}</td><td>{{p.tipo}}</td><td>{{p.status}}</td>
<td>{{p.palet or '-'}}</td><td>{{p.destino or '-'}}</td>
<td>{% if p.status in ('NO_PALET','DESTINO_DEFINIDO') %}
<form method="post" action="/produtos/{{p.id}}/destino">
<select name="destino_id">{% for d in destinos %}<option value="{{d.id}}">{{d.nome}}</option>{% endfor %}</select>
<button>Salvar</button></form>
{% elif p.status == 'ENTREGUE' %}-{% else %}(aguardando chegar ao palet){% endif %}</td></tr>
{% endfor %}
</table>

<h2>3. Simular leitura de tag (no lugar do Arduino)</h2>
<form method="post" action="/simular">
  Produto: <select name="uid">{% for p in produtos %}<option value="{{p.tag_uid}}">{{p.tag_uid}} ({{p.tipo}})</option>{% endfor %}</select>
  Leitor: <select name="leitor">{% for l in leitores %}<option value="{{l.codigo}}">{{l.codigo}}</option>{% endfor %}</select>
  <button>Ler tag</button>
</form>

<h2>4. Porta-palets</h2>
<table border="1" cellpadding="4">
<tr><th>Palet</th><th>Tipo</th><th>Produtos nele</th></tr>
{% for pp in palets %}<tr><td>{{pp.codigo}}</td><td>{{pp.tipo}}</td><td>{{pp.qtd}}</td></tr>{% endfor %}
</table>

<h2>5. Docas</h2>
<table border="1" cellpadding="4">
<tr><th>Doca</th><th>Tipo</th><th>Destino</th></tr>
{% for d in docas %}<tr><td>{{d.codigo}}</td><td>{{d.tipo}}</td><td>{{d.destino or '-'}}</td></tr>{% endfor %}
</table>

<h2>6. Ultimos eventos</h2>
<table border="1" cellpadding="4">
<tr><th>Data/hora</th><th>UID</th><th>Leitor</th><th>OK?</th><th>Resultado</th></tr>
{% for e in eventos %}<tr><td>{{e.data_hora}}</td><td>{{e.tag_uid}}</td><td>{{e.leitor or '-'}}</td>
<td>{{'sim' if e.sucesso else 'NAO'}}</td><td>{{e.resultado}}</td></tr>{% endfor %}
</table>
<script>
let ultimaSeq = {{ ultima.seq if ultima else 0 }};
setInterval(async () => {
  try {
    const r = await (await fetch('/api/ultima-leitura')).json();
    if (r.seq > ultimaSeq) {
      ultimaSeq = r.seq;
      document.getElementById('campo-uid').value = r.uid;
      document.getElementById('ultima-uid').textContent = r.uid;
    }
  } catch (e) {}
}, 1000);
</script>
</body></html>"""


@app.get("/")
def index():
    db = get_db()
    q = lambda sql: db.execute(sql).fetchall()
    return render_template_string(
        PAGINA,
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
    if alvo != "CADASTRO" and not db.execute("SELECT 1 FROM leitores WHERE codigo=?", (alvo,)).fetchone():
        return voltar("Leitor invalido.")
    db.execute("UPDATE config SET valor=? WHERE chave='leitor_ativo'", (alvo,))
    db.commit()
    return voltar(f"Leitor fisico agora funciona como: {alvo}")


@app.post("/simular")
def simular():
    ok, msg = processar_leitura(get_db(), request.form["uid"], request.form["leitor"])
    return voltar(("OK: " if ok else "ERRO: ") + msg)


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
