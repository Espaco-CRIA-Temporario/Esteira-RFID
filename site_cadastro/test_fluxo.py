"""Testa o site, as regras e o banco SEM Arduino:  python test_fluxo.py"""
import os
import sqlite3
import tempfile

PASTA = tempfile.mkdtemp()
os.environ["ARMAZEM_DB"] = os.path.join(PASTA, "teste.db")

import app as A  # noqa: E402
import banco  # noqa: E402
import regras  # noqa: E402

c = A.app.test_client()
falhas = 0


def check(nome, cond):
    global falhas
    print(("OK   " if cond else "FALHA"), nome)
    if not cond:
        falhas += 1


def msgs():
    """Le e limpa as mensagens de aviso mostradas pelo site (flash)."""
    with c.session_transaction() as sess:
        return [m for _, m in sess.pop("_flashes", [])]


def post(url, **dados):
    """Faz um POST de formulario e devolve as mensagens de aviso que o site gerou."""
    msgs()
    c.post(url, data=dados)
    return msgs()


def tag(uid, sensor=None):
    corpo = {"uid": uid}
    if sensor:
        corpo["sensor"] = sensor
    r = c.post("/api/tag-lida", json=corpo)
    return r.status_code, r.get_json()


def status_de(uid):
    return c.get(f"/api/produtos/{uid}").get_json()["status"]


def cadastrar(uid, tipo_id):
    c.post("/produtos", data={"uid": uid, "tipo_produto_id": tipo_id})


def destino(uid, destino_id):
    with A.app.app_context():
        pid = banco.get_db().execute("SELECT id FROM produtos WHERE tag_uid=?", (uid,)).fetchone()[0]
        return regras.definir_destino(banco.get_db(), pid, destino_id)


# ------------------------------------------------------------------ banco novo
with A.app.app_context():
    db = banco.get_db()
    n = lambda t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    check("4 tipos de TV", n("tipos_produto") == 4)
    check("4 ruas (uma por tipo)", n("ruas") == 4)
    check("2 porta-pallets em cada rua", db.execute("SELECT COUNT(*) FROM ruas WHERE porta_pallets=2").fetchone()[0] == 4)
    check("4 docas", n("docas") == 4)
    check("4 destinos, cada um com uma doca", db.execute("SELECT COUNT(*) FROM destinos WHERE doca_id IS NOT NULL").fetchone()[0] == 4)
    check("4 sensores", n("sensores") == 4)

# ------------------------------------------------------------------ fluxo completo (TV 50 = tipo 2, rua 2)
cadastrar("AA11BB22", 2)
check("produto cadastrado", status_de("AA11BB22") == "CADASTRADO")
check("UID repetido no cadastro e recusado", any("ja esta cadastrado" in m for m in post("/produtos", uid="AA11BB22", tipo_produto_id=2)))
check("destino recusado antes da rua (CADASTRADO)", not destino("AA11BB22", 3).ok)

s, j = tag("AA11BB22", "SENSOR-ESTEIRA-INICIO")
check("esteira inicio recusa produto que nao passou na doca", s == 422 and j["comando"] is None)

s, j = tag("AA11BB22", "SENSOR-DOCA-ENTRADA")
check("doca de entrada -> NA_DOCA", s == 200 and status_de("AA11BB22") == "NA_DOCA")
check("doca de entrada nao repete", tag("AA11BB22", "SENSOR-DOCA-ENTRADA")[0] == 422)
check("destino recusado enquanto NA_DOCA", not destino("AA11BB22", 3).ok)

s, j = tag("AA11BB22", "SENSOR-ESTEIRA-INICIO")
check("inicio da esteira -> NA_RUA e comando RUA:2", s == 200 and j["comando"] == "RUA:2" and status_de("AA11BB22") == "NA_RUA")
check("rua gravada no produto", c.get("/api/produtos/AA11BB22").get_json()["rua"] == "RUA 2")

s, j = tag("AA11BB22", "SENSOR-ESTEIRA-FIM")
check("fim da esteira sem destino e recusado", s == 422 and j["comando"] is None and "destino" in j["mensagem"].lower())

check("destino aceito na rua", destino("AA11BB22", 3).ok and status_de("AA11BB22") == "DESTINO_DEFINIDO")
check("destino pode ser trocado enquanto na rua", destino("AA11BB22", 4).ok and destino("AA11BB22", 3).ok)

s, j = tag("AA11BB22", "SENSOR-DOCA-SAIDA")
check("doca de saida antes da esteira e recusada", s == 422)

s, j = tag("AA11BB22", "SENSOR-ESTEIRA-FIM")
check("fim da esteira -> NA_ESTEIRA e comando DOCA:3", s == 200 and j["comando"] == "DOCA:3" and status_de("AA11BB22") == "NA_ESTEIRA")
check("destino nao muda depois que saiu da rua", not destino("AA11BB22", 1).ok)

s, j = tag("AA11BB22", "SENSOR-DOCA-SAIDA")
check("doca de saida -> EXPEDIDO", s == 200 and status_de("AA11BB22") == "EXPEDIDO")
check("produto expedido nao entra de novo", tag("AA11BB22", "SENSOR-DOCA-ENTRADA")[0] == 422)

# ------------------------------------------------------------------ erros
check("tag desconhecida", tag("FFFFFFFF", "SENSOR-DOCA-ENTRADA")[0] == 422)
check("sensor desconhecido", tag("AA11BB22", "SENSOR-NAO-EXISTE")[0] == 422)
check("UID vazio da 400", tag("  ")[0] == 400)

# ------------------------------------------------------------------ modo CADASTRO (leitor fisico)
s, j = tag("1122 3344")
check("modo CADASTRO captura o UID", s == 200 and j["ok"] and j["comando"] is None)
u = c.get("/api/ultima-leitura").get_json()
check("ultima leitura normalizada", u["uid"] == "11223344" and u["seq"] == 1)
tag("55667788")
check("seq sobe a cada leitura", c.get("/api/ultima-leitura").get_json()["seq"] == 2)
check("UID ja cadastrado e recusado no cadastro", tag("AA11BB22")[0] == 422)

# trocar o sensor ativo no site e ler sem informar o sensor
cadastrar("11223344", 1)   # TV 45 -> rua 1
c.post("/sensor-ativo", data={"sensor": "SENSOR-DOCA-ENTRADA"})
s, j = tag("11223344")
check("sensor ativo vale quando a ponte nao informa o sensor", s == 200 and status_de("11223344") == "NA_DOCA")
c.post("/sensor-ativo", data={"sensor": "SENSOR-ESTEIRA-INICIO"})
s, j = tag("11223344")
check("sensor ativo ESTEIRA-INICIO manda RUA:1", s == 200 and j["comando"] == "RUA:1")
check("sensor ativo invalido e recusado", any("invalido" in m.lower() for m in post("/sensor-ativo", sensor="INVALIDO")))
check("sensor ativo continua o anterior", b"<b>SENSOR-ESTEIRA-INICIO</b>" in c.get("/").data)
c.post("/sensor-ativo", data={"sensor": "CADASTRO"})

# ------------------------------------------------------------------ casos de configuracao
# tipo sem rua
c.post("/cadastros/tipos", data={"nome": "TV 65", "polegadas": 65})
with A.app.app_context():
    tipo65 = banco.get_db().execute("SELECT id FROM tipos_produto WHERE nome='TV 65'").fetchone()[0]
cadastrar("65656565", tipo65)
tag("65656565", "SENSOR-DOCA-ENTRADA")
s, j = tag("65656565", "SENSOR-ESTEIRA-INICIO")
check("tipo sem rua cadastrada e recusado", s == 422 and "rua" in j["mensagem"].lower())

# destino sem doca
c.post("/cadastros/destinos", data={"nome": "Destino 5", "doca_id": ""})
with A.app.app_context():
    d5 = banco.get_db().execute("SELECT id FROM destinos WHERE nome='Destino 5'").fetchone()[0]
cadastrar("77777777", 1)
tag("77777777", "SENSOR-DOCA-ENTRADA"); tag("77777777", "SENSOR-ESTEIRA-INICIO")
destino("77777777", d5)
s, j = tag("77777777", "SENSOR-ESTEIRA-FIM")
check("destino sem doca e recusado no fim da esteira", s == 422 and "doca" in j["mensagem"].lower())

# sensor de saida preso a uma doca: so aceita o destino daquela doca
with A.app.app_context():
    db = banco.get_db()
    db.execute("UPDATE sensores SET doca_id=(SELECT id FROM docas WHERE numero=1) WHERE codigo='SENSOR-DOCA-SAIDA'")
    db.commit()
cadastrar("88888888", 3)   # TV 55
for sensor in ("SENSOR-DOCA-ENTRADA", "SENSOR-ESTEIRA-INICIO"):
    tag("88888888", sensor)
destino("88888888", 2)     # Destino 2 -> DOCA 2
tag("88888888", "SENSOR-ESTEIRA-FIM")
s, j = tag("88888888", "SENSOR-DOCA-SAIDA")
check("sensor de saida da doca errada e recusado", s == 422 and "ERRADA" in j["mensagem"])

# ------------------------------------------------------------------ editar o banco pelo site (Cadastros)
check("adicionar doca mostra aviso", post("/cadastros/docas", codigo="DOCA 5", numero=5) == ["Adicionado."])
with A.app.app_context():
    d = banco.get_db().execute("SELECT id FROM docas WHERE numero=5").fetchone()
check("adicionar doca pelo site", d is not None)
check("editar doca mostra aviso", post(f"/cadastros/docas/{d[0]}", codigo="DOCA CINCO", numero=5) == ["Salvo."])
with A.app.app_context():
    check("editar doca pelo site", banco.get_db().execute("SELECT codigo FROM docas WHERE numero=5").fetchone()[0] == "DOCA CINCO")
check("numero de doca repetido e recusado", any("Ja existe" in m for m in post("/cadastros/docas", codigo="OUTRA", numero=5)))
check("numero invalido e recusado", any("precisa ser um numero" in m for m in post("/cadastros/docas", codigo="X", numero="abc")))
check("campo obrigatorio vazio e recusado", any("Preencha" in m for m in post("/cadastros/docas", codigo="", numero=9)))
check("doca em uso nao pode ser excluida", any("usado em outra tabela" in m for m in post("/cadastros/docas/1/excluir")))
c.post(f"/cadastros/docas/{d[0]}/excluir")
with A.app.app_context():
    check("excluir doca sem uso", banco.get_db().execute("SELECT 1 FROM docas WHERE numero=5").fetchone() is None)
check("opcao invalida em lista e recusada", any("invalido" in m.lower() for m in post("/cadastros/sensores/1", codigo="SENSOR-DOCA-ENTRADA", local="INEXISTENTE", doca_id="")))

# editar produto direto: voltar o status para refazer um teste
with A.app.app_context():
    pid = banco.get_db().execute("SELECT id FROM produtos WHERE tag_uid='AA11BB22'").fetchone()[0]
c.post(f"/cadastros/produtos/{pid}", data={"tag_uid": "AA11BB22", "tipo_produto_id": 2, "status": "CADASTRADO", "rua_id": "", "destino_id": ""})
check("produto editado direto volta a CADASTRADO", status_de("AA11BB22") == "CADASTRADO")

# ------------------------------------------------------------------ paginas
for url in ("/", "/produtos", "/armazem", "/eventos", "/banco", "/cadastros", "/cadastros/tipos", "/cadastros/ruas",
            "/cadastros/docas", "/cadastros/destinos", "/cadastros/sensores", "/cadastros/produtos",
            "/static/estilo.css", "/static/app.js", "/api/produtos"):
    r = c.get(url, follow_redirects=True)
    check(f"pagina {url} abre", r.status_code == 200)
check("cadastro desconhecido volta ao inicio", c.get("/cadastros/xyz", follow_redirects=True).status_code == 200)
check("/banco mostra as tabelas novas", all(t.encode() in c.get("/banco").data for t in ("eventos", "ruas", "sensores")))
check("/produtos traz o campo do leitor", b'id="campo-uid"' in c.get("/produtos").data)
check("armazem lista as 4 ruas", c.get("/armazem").data.count(b"RUA:") >= 4)

# ------------------------------------------------------------------ banco antigo / migracao
antigo = os.path.join(PASTA, "antigo.db")
con = sqlite3.connect(antigo)
con.executescript("CREATE TABLE docas (id INTEGER PRIMARY KEY, codigo TEXT); INSERT INTO docas VALUES (1,'ENT-1');")
con.commit(); con.close()
backup = banco.init_db(antigo)
con = sqlite3.connect(antigo)
check("banco de versao antiga vira backup", backup is not None and os.path.exists(backup))
check("banco novo e criado no lugar", con.execute("SELECT COUNT(*) FROM ruas").fetchone()[0] == 4)
con.close()
check("backup guarda os dados antigos", sqlite3.connect(backup).execute("SELECT codigo FROM docas").fetchone()[0] == "ENT-1")
check("banco na versao certa nao e tocado", banco.init_db(antigo) is None)
vazio = os.path.join(PASTA, "vazio.db")
open(vazio, "w").close()
check("arquivo de banco vazio (0 bytes) e aproveitado", banco.init_db(vazio) is None and sqlite3.connect(vazio).execute("SELECT COUNT(*) FROM tipos_produto").fetchone()[0] == 4)

print("\nFalhas:", falhas)
raise SystemExit(1 if falhas else 0)
