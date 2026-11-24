"""Site e API. So as rotas: as regras ficam em regras.py, o banco em banco.py,
as tabelas editaveis em cadastros.py, o HTML em templates/ e o visual em static/estilo.css."""
import os

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

import banco
import cadastros
import regras
from banco import get_db
from regras import LOCAIS_SENSOR, MODO_CADASTRO, STATUS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "armazem-chave-de-desenvolvimento")
banco.init_app(app)

# Disponiveis em todos os templates
app.jinja_env.globals.update(
    STATUS=STATUS, LOCAIS=LOCAIS_SENSOR, CADASTROS=cadastros.CADASTROS, rotulo_status=regras.rotulo_status,
)


@app.context_processor
def contexto_comum():
    return {"leitor_atual": banco.sensor_ativo(get_db())}


def avisar(resultado, destino, **params):
    """Mostra a mensagem do resultado no topo da proxima pagina e volta para 'destino'."""
    flash(resultado.mensagem, "ok" if resultado.ok else "erro")
    return redirect(url_for(destino, **params))


def consulta(sql, *params):
    return get_db().execute(sql, params).fetchall()


SQL_PRODUTOS = """SELECT p.id, p.tag_uid, p.status, p.atualizado_em, t.nome AS tipo,
                         r.codigo AS rua, d.nome AS destino, d.id AS destino_id
                  FROM produtos p JOIN tipos_produto t ON t.id = p.tipo_produto_id
                  LEFT JOIN ruas r ON r.id = p.rua_id
                  LEFT JOIN destinos d ON d.id = p.destino_id"""

SQL_EVENTOS = """SELECT e.*, s.codigo AS sensor FROM eventos e
                 LEFT JOIN sensores s ON s.id = e.sensor_id ORDER BY e.id DESC LIMIT ?"""


# ================================================================ paginas
@app.get("/")
def painel():
    por_status = {r["status"]: r["qtd"] for r in consulta("SELECT status, COUNT(*) AS qtd FROM produtos GROUP BY status")}
    return render_template(
        "painel.html",
        fluxo=[(codigo, nome, por_status.get(codigo, 0)) for codigo, nome in STATUS.items()],
        sensores=consulta("SELECT * FROM sensores ORDER BY id"),
        produtos=consulta(SQL_PRODUTOS + " ORDER BY p.id"),
        ultima=get_db().execute("SELECT * FROM ultima_leitura WHERE id=1").fetchone(),
        eventos=consulta(SQL_EVENTOS, 10),
    )


@app.get("/produtos")
def produtos():
    return render_template(
        "produtos.html",
        tipos=consulta("SELECT * FROM tipos_produto ORDER BY polegadas"),
        destinos=consulta("SELECT * FROM destinos ORDER BY nome"),
        produtos=consulta(SQL_PRODUTOS + " ORDER BY p.id DESC"),
        pode_definir=regras.PODE_DEFINIR_DESTINO,
        ultima=get_db().execute("SELECT * FROM ultima_leitura WHERE id=1").fetchone(),
    )


@app.get("/armazem")
def armazem():
    ativos = consulta(SQL_PRODUTOS + " WHERE p.status IN ('NA_RUA','DESTINO_DEFINIDO') ORDER BY p.id")
    ruas = []
    for r in consulta("""SELECT r.*, t.nome AS tipo FROM ruas r
                         JOIN tipos_produto t ON t.id = r.tipo_produto_id ORDER BY r.numero"""):
        ruas.append({"rua": r, "produtos": [p for p in ativos if p["rua"] == r["codigo"]]})
    docas = consulta("""SELECT c.*,
        (SELECT group_concat(nome, ', ') FROM destinos WHERE doca_id = c.id) AS destinos,
        (SELECT COUNT(*) FROM produtos p JOIN destinos d ON d.id = p.destino_id
          WHERE d.doca_id = c.id AND p.status = 'NA_ESTEIRA') AS saindo,
        (SELECT COUNT(*) FROM produtos p JOIN destinos d ON d.id = p.destino_id
          WHERE d.doca_id = c.id AND p.status = 'EXPEDIDO') AS expedidos
        FROM docas c ORDER BY c.numero""")
    transito = {r["status"]: r["qtd"] for r in consulta(
        "SELECT status, COUNT(*) AS qtd FROM produtos WHERE status IN ('NA_DOCA','NA_ESTEIRA') GROUP BY status")}
    return render_template("armazem.html", ruas=ruas, docas=docas, transito=transito)


@app.get("/eventos")
def eventos():
    return render_template("eventos.html", eventos=consulta(SQL_EVENTOS, 100))


@app.get("/banco")
def ver_banco():
    """Mostra o conteudo de todas as tabelas (so leitura), para conferir o banco pelo navegador."""
    return render_template("banco.html", dados=banco.tabelas(get_db()), arquivo=banco.DB)


# ================================================================ acoes dos formularios
@app.post("/produtos")
def produto_novo():
    r = regras.cadastrar_produto(get_db(), request.form.get("uid"), request.form.get("tipo_produto_id"))
    return avisar(r, "produtos")


@app.post("/produtos/<int:produto_id>/destino")
def produto_destino(produto_id):
    r = regras.definir_destino(get_db(), produto_id, request.form.get("destino_id"))
    return avisar(r, "produtos")


@app.post("/sensor-ativo")
def trocar_sensor_ativo():
    db = get_db()
    alvo = request.form.get("sensor", MODO_CADASTRO)
    if alvo != MODO_CADASTRO and not db.execute("SELECT 1 FROM sensores WHERE codigo=?", (alvo,)).fetchone():
        flash("Sensor invalido.", "erro")
    else:
        db.execute("UPDATE config SET valor=? WHERE chave='sensor_ativo'", (alvo,))
        db.commit()
        flash(f"O leitor fisico agora funciona como: {alvo}", "ok")
    return redirect(url_for("painel"))


@app.post("/simular")
def simular():
    """Faz de conta que um sensor leu uma tag (para testar sem Arduino)."""
    r = regras.processar_leitura(get_db(), request.form.get("uid"), request.form.get("sensor"))
    extra = f" Comando para a esteira: {r.comando}" if r.comando else ""
    flash(("OK: " if r.ok else "ERRO: ") + r.mensagem + extra, "ok" if r.ok else "erro")
    return redirect(url_for("painel"))


# ================================================================ cadastros (editar o banco)
def _cfg(chave):
    cfg = cadastros.CADASTROS.get(chave)
    if not cfg:
        flash("Cadastro desconhecido.", "erro")
    return cfg


@app.get("/cadastros")
def cadastros_inicio():
    return redirect(url_for("cadastro", chave=next(iter(cadastros.CADASTROS))))


@app.get("/cadastros/<chave>")
def cadastro(chave):
    cfg = _cfg(chave)
    if not cfg:
        return redirect(url_for("cadastros_inicio"))
    db = get_db()
    return render_template("cadastro.html", chave=chave, cfg=cfg,
                           linhas=cadastros.linhas(db, cfg), opcoes=cadastros.opcoes(db, cfg))


def _gravar(chave, id=None):
    cfg = _cfg(chave)
    if not cfg:
        return redirect(url_for("cadastros_inicio"))
    try:
        ok, msg = cadastros.salvar(get_db(), cfg, cadastros.ler_formulario(cfg, request.form), id)
    except ValueError as e:
        ok, msg = False, str(e)
    flash(msg, "ok" if ok else "erro")
    return redirect(url_for("cadastro", chave=chave))


@app.post("/cadastros/<chave>")
def cadastro_novo(chave):
    return _gravar(chave)


@app.post("/cadastros/<chave>/<int:id>")
def cadastro_salvar(chave, id):
    return _gravar(chave, id)


@app.post("/cadastros/<chave>/<int:id>/excluir")
def cadastro_excluir(chave, id):
    cfg = _cfg(chave)
    if not cfg:
        return redirect(url_for("cadastros_inicio"))
    ok, msg = cadastros.excluir(get_db(), cfg, id)
    flash(msg, "ok" if ok else "erro")
    return redirect(url_for("cadastro", chave=chave))


# ================================================================ API (ponte / esteira)
@app.post("/api/tag-lida")
def api_tag_lida():
    """Usada pela ponte USB. Corpo: {"uid": "04A1B2C3"}  (opcional: "sensor": "SENSOR-...").
    Sem "sensor" vale o sensor ativo escolhido no site.
    Resposta: {ok, mensagem, comando}. 'comando' e o texto para a esteira (ex.: "RUA:2"), ou null."""
    d = request.get_json(silent=True) or {}
    if not banco.normalizar_uid(d.get("uid")):
        return jsonify(ok=False, mensagem="UID vazio.", comando=None), 400
    r = regras.tag_lida(get_db(), d.get("uid"), d.get("sensor"))
    return jsonify(ok=r.ok, mensagem=r.mensagem, comando=r.comando), (200 if r.ok else 422)


@app.get("/api/ultima-leitura")
def api_ultima_leitura():
    r = get_db().execute("SELECT seq, tag_uid, data_hora FROM ultima_leitura WHERE id=1").fetchone()
    return jsonify(seq=r["seq"], uid=r["tag_uid"], data_hora=r["data_hora"]) if r else jsonify(seq=0, uid="", data_hora="")


@app.get("/api/produtos")
def api_produtos():
    return jsonify([dict(r) for r in consulta(SQL_PRODUTOS + " ORDER BY p.id")])


@app.get("/api/produtos/<uid>")
def api_produto(uid):
    r = get_db().execute(SQL_PRODUTOS + " WHERE p.tag_uid=?", (banco.normalizar_uid(uid),)).fetchone()
    return (jsonify(dict(r)), 200) if r else (jsonify(ok=False, mensagem="Tag nao cadastrada."), 404)


banco.init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
