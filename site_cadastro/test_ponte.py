"""Testa a ponte.py sem Arduino: usa portas seriais falsas e o site de verdade (em segundo plano)."""
import os
import tempfile
import threading

os.environ["ARMAZEM_DB"] = os.path.join(tempfile.mkdtemp(), "teste.db")

import requests  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

import app as A  # noqa: E402
import regras  # noqa: E402
import ponte  # noqa: E402

srv = make_server("127.0.0.1", 5057, A.app)
threading.Thread(target=srv.serve_forever, daemon=True).start()
API = "http://127.0.0.1:5057"
falhas = 0


def check(nome, cond):
    global falhas
    print(("OK   " if cond else "FALHA"), nome)
    if not cond:
        falhas += 1


class Fake:
    def __init__(self, entrada=()):
        self.saida, self.entrada = [], [l.encode() + b"\n" for l in entrada]

    def write(self, b):
        self.saida.append(b.decode().strip())

    @property
    def in_waiting(self):
        return len(self.entrada)

    def readline(self):
        return self.entrada.pop(0) if self.entrada else b""


def passo(uid, leitor=None, esteira=True, docas=3):
    L, E = Fake(), Fake()
    ponte.tratar_linha(f"UID;{uid}", API, leitor, L, E if esteira else None, docas)
    return L.saida, E.saida


check("linha INFO e ignorada", ponte.tratar_linha("INFO;PN532 pronto", API, None, Fake(), Fake()) is None)

# cadastro pela tag
L, E = passo("04A1B2C3")
check("cadastro: leitor recebe OK, esteira nada", L == ["OK"] and E == [])
uid = requests.get(API + "/api/ultima-leitura").json()["uid"]
check("UID chegou ao site", uid == "04A1B2C3")
requests.post(API + "/produtos", data={"uid": uid, "tipo_id": 3}, allow_redirects=False)  # TV 55
check("tag repetida no cadastro da ERRO", passo("04A1B2C3")[0] == ["ERRO"])

# operacao ate a esteira
check("entrada OK", passo("04A1B2C3", "LEITOR-ENT-1")[0] == ["OK"])
check("palet certo OK", passo("04A1B2C3", "LEITOR-PP-TV55-B")[0] == ["OK"])
check("esteira sem destino recusa", passo("04A1B2C3", "ESTEIRA") == (["ERRO"], []))
requests.post(API + "/produtos/1/destino", data={"destino_id": 2})
L, E = passo("04A1B2C3", "ESTEIRA")
check("esteira recebe CAIXA:2 e leitor OK", L == ["OK"] and E == ["CAIXA:2"])
check("mesma caixa nao entra de novo", passo("04A1B2C3", "ESTEIRA") == (["ERRO"], []))

# destino 4 nao existe na esteira de 3 docas
requests.post(API + "/produtos", data={"uid": "AA000004", "tipo_id": 1})
passo("AA000004", "LEITOR-ENT-2"); passo("AA000004", "LEITOR-PP-TV45-A")
requests.post(API + "/produtos/2/destino", data={"destino_id": 4})
check("destino 4 com esteira de 3 docas: site recusa e nada e enviado", passo("AA000004", "ESTEIRA") == (["ERRO"], []))
st = requests.get(API + "/api/produtos").json()[1]["status"]
check("produto recusado continua com destino definido", st == "DESTINO_DEFINIDO")
requests.post(API + "/produtos", data={"uid": "AA000005", "tipo_id": 1})
passo("AA000005", "LEITOR-ENT-2"); passo("AA000005", "LEITOR-PP-TV45-A")
requests.post(API + "/produtos/3/destino", data={"destino_id": 4})
regras.ESTEIRA_DOCAS = 4   # simula uma esteira de 4 docas
check("com docas=4 envia CAIXA:4", passo("AA000005", "ESTEIRA", docas=4) == (["OK"], ["CAIXA:4"]))

# sem esteira conectada
requests.post(API + "/produtos", data={"uid": "AA000006", "tipo_id": 1})
passo("AA000006", "LEITOR-ENT-2"); passo("AA000006", "LEITOR-PP-TV45-A")
requests.post(API + "/produtos/4/destino", data={"destino_id": 1})
check("sem --esteira: nao quebra", passo("AA000006", "ESTEIRA", esteira=False)[0] == ["OK"])

# mensagens da esteira
L, E = Fake(), Fake(["# debug qualquer", "ERRO"])
ponte.ler_esteira(E, L)
check("ERRO da esteira faz o leitor apitar", L.saida == ["ERRO"])

# site fora do ar
L = Fake()
ponte.tratar_linha("UID;AAAA", "http://127.0.0.1:9", None, L, Fake())
check("site fora do ar: leitor recebe ERRO", L.saida == ["ERRO"])

print("\nFalhas:", falhas)
raise SystemExit(1 if falhas else 0)
