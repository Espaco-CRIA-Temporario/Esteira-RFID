import os
import tempfile

os.environ["ARMAZEM_DB"] = os.path.join(tempfile.mkdtemp(), "teste.db")

import app as A  # noqa: E402

c = A.app.test_client()
falhas = 0


def check(nome, cond):
    global falhas
    print(("OK   " if cond else "FALHA"), nome)
    if not cond:
        falhas += 1


def leitura(uid, leitor):
    r = c.post("/api/leituras", json={"uid": uid, "leitor": leitor})
    return r.status_code, r.get_json()["mensagem"]


with A.app.app_context():
    db = A.get_db()
    n = lambda t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    check("4 tipos de TV", n("tipos_produto") == 4)
    check("8 docas (4 entrada + 4 saida)", n("docas") == 8)
    check("8 porta-palets", n("porta_palets") == 8)
    check("4 destinos", n("destinos") == 4)
    check("16 leitores (8 docas + 8 palets)", n("leitores") == 16)

# cadastro
c.post("/produtos", data={"uid": "AA11BB22", "tipo_id": 2})  # TV 50
check("cadastro duplicado e recusado", "ja%20esta%20cadastrado" in c.post("/produtos", data={"uid": "AA11BB22", "tipo_id": 2}).headers["Location"])

# regra: destino antes do palet deve ser recusado no backend
with A.app.app_context():
    ok, msg = A.definir_destino(A.get_db(), 1, 3)
check("destino recusado enquanto CADASTRADO", not ok)

# doca de entrada
s, m = leitura("AA11BB22", "LEITOR-ENT-1")
check("doca de entrada -> NA_DOCA", s == 200)
with A.app.app_context():
    ok, _ = A.definir_destino(A.get_db(), 1, 3)
check("destino recusado enquanto NA_DOCA", not ok)

# palet errado (TV 45) e palet certo (TV 50)
s, m = leitura("AA11BB22", "LEITOR-PP-TV45-A")
check("palet errado e recusado", s == 422 and "ERRADO" in m)
s, m = leitura("AA11BB22", "LEITOR-PP-TV50-B")
check("palet certo -> NO_PALET", s == 200)

# esteira ainda sem destino
r = c.get("/api/produtos/AA11BB22/destino")
check("esteira: sem destino -> 409", r.status_code == 409)

# define destino 3
with A.app.app_context():
    ok, _ = A.definir_destino(A.get_db(), 1, 3)
check("destino aceito apos NO_PALET", ok)
r = c.get("/api/produtos/AA11BB22/destino").get_json()
check("esteira recebe rota 3", r["ok"] and r["rota"] == 3)

# doca de saida errada e certa
s, m = leitura("AA11BB22", "LEITOR-SAI-1")
check("doca de saida errada e recusada", s == 422)
s, m = leitura("AA11BB22", "LEITOR-SAI-3")
check("doca de saida certa -> ENTREGUE", s == 200)

with A.app.app_context():
    st = A.get_db().execute("SELECT status FROM produtos WHERE id=1").fetchone()[0]
check("status final ENTREGUE", st == "ENTREGUE")

check("tag desconhecida", leitura("FFFFFFFF", "LEITOR-ENT-1")[0] == 422)
check("pagina inicial abre", c.get("/").status_code == 200)

# ---- integracao com o leitor fisico ----
def tag(uid, leitor=None):
    corpo = {"uid": uid}
    if leitor:
        corpo["leitor"] = leitor
    r = c.post("/api/tag-lida", json=corpo)
    return r.status_code, r.get_json()


# modo CADASTRO (padrao): so captura o UID
s, j = tag("1122 3344")
check("tag no modo CADASTRO e capturada", s == 200 and j["ok"] and not j["esteira"])
u = c.get("/api/ultima-leitura").get_json()
check("ultima leitura guarda UID normalizado", u["uid"] == "11223344" and u["seq"] == 1)
tag("55667788")
check("seq aumenta a cada leitura", c.get("/api/ultima-leitura").get_json()["seq"] == 2)
check("UID ja cadastrado e recusado no cadastro", tag("AA11BB22")[0] == 422)
check("UID vazio da 400", tag("  ")[0] == 400)

# cadastra pelo UID capturado e roda a operacao inteira pelo endpoint unico
c.post("/produtos", data={"uid": "11223344", "tipo_id": 4})  # TV 60 -> id 2
c.post("/leitor-ativo", data={"leitor": "LEITOR-ENT-2"})
s, j = tag("11223344")
check("leitor ativo = doca de entrada", s == 200 and "doca" in j["mensagem"].lower())
check("leitor invalido e recusado", "invalido" in c.post("/leitor-ativo", data={"leitor": "XYZ"}).headers["Location"].lower())
s, j = tag("11223344", "LEITOR-PP-TV55-A")
check("palet errado via endpoint unico", s == 422)
s, j = tag("11223344", "LEITOR-PP-TV60-A")
check("palet certo via endpoint unico", s == 200 and not j["esteira"])
with A.app.app_context():
    A.definir_destino(A.get_db(), 2, 4)
s, j = tag("11223344", "LEITOR-SAI-4")
check("doca de saida certa aciona a esteira com rota 4", s == 200 and j["esteira"] and j["rota"] == 4)
check("pagina com leitor fisico abre", b"campo-uid" in c.get("/").data)
r = c.get("/banco")
check("pagina /banco mostra as tabelas e os dados", r.status_code == 200 and b"eventos_leitura" in r.data and b"11223344" in r.data)

# ---- leitor ESTEIRA (inicio da esteira) ----
c.post("/produtos", data={"uid": "ABCD0001", "tipo_id": 1})  # TV 45 -> id 3
s, j = tag("ABCD0001", "ESTEIRA")
check("ESTEIRA recusa produto sem destino", s == 422 and not j["esteira"])
tag("ABCD0001", "LEITOR-ENT-3")
tag("ABCD0001", "LEITOR-PP-TV45-B")
with A.app.app_context():
    A.definir_destino(A.get_db(), 3, 2)
s, j = tag("ABCD0001", "ESTEIRA")
check("ESTEIRA libera produto com destino 2", s == 200 and j["esteira"] and j["rota"] == 2)
s, j = tag("ABCD0001", "ESTEIRA")
check("ESTEIRA nao libera o mesmo produto duas vezes", s == 422 and not j["esteira"])
check("ESTEIRA com tag desconhecida", tag("00000000", "ESTEIRA")[0] == 422)
c.post("/leitor-ativo", data={"leitor": "ESTEIRA"})
check("leitor ativo pode ser ESTEIRA", b'value="ESTEIRA" selected' in c.get("/").data)

print("\nFalhas:", falhas)
raise SystemExit(1 if falhas else 0)
