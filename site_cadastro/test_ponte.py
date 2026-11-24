"""Testa a ponte.py sem Arduino: usa portas seriais falsas e o site de verdade (em segundo plano).
Uso:  python test_ponte.py"""
import os
import tempfile
import threading

os.environ["ARMAZEM_DB"] = os.path.join(tempfile.mkdtemp(), "teste.db")

import requests  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

import app as A  # noqa: E402
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
    """Porta serial falsa: guarda o que a ponte escreve e entrega linhas prontas para ler."""
    def __init__(self, entrada=()):
        self.saida, self.entrada = [], [l.encode() + b"\n" for l in entrada]

    def write(self, b):
        self.saida.append(b.decode().strip())

    @property
    def in_waiting(self):
        return len(self.entrada)

    def readline(self):
        return self.entrada.pop(0) if self.entrada else b""


def passo(uid, sensor=None, esteira=True):
    """Simula uma leitura. Retorna (o que o leitor recebeu, o que a esteira recebeu)."""
    L, E = Fake(), Fake()
    ponte.tratar_linha(f"UID;{uid}", API, sensor, L, E if esteira else None)
    return L.saida, E.saida


def definir_destino(pid, destino_id):
    requests.post(f"{API}/produtos/{pid}/destino", data={"destino_id": destino_id})


check("linha INFO e ignorada", ponte.tratar_linha("INFO;PN532 pronto", API, None, Fake(), Fake()) is None)

# cadastro pela tag (sensor ativo = CADASTRO)
check("cadastro: leitor OK e esteira sem comando", passo("04A1B2C3") == (["OK"], []))
uid = requests.get(API + "/api/ultima-leitura").json()["uid"]
check("UID chegou ao site", uid == "04A1B2C3")
requests.post(API + "/produtos", data={"uid": uid, "tipo_produto_id": 3})   # TV 55 -> RUA 3
check("tag repetida no cadastro da ERRO", passo("04A1B2C3") == (["ERRO"], []))

# fluxo completo, mandando o sensor
check("doca de entrada: OK sem comando", passo("04A1B2C3", "SENSOR-DOCA-ENTRADA") == (["OK"], []))
check("inicio da esteira: esteira recebe RUA:3", passo("04A1B2C3", "SENSOR-ESTEIRA-INICIO") == (["OK"], ["RUA:3"]))
check("fim da esteira sem destino: ERRO e nada enviado", passo("04A1B2C3", "SENSOR-ESTEIRA-FIM") == (["ERRO"], []))
definir_destino(1, 2)
check("fim da esteira: esteira recebe DOCA:2", passo("04A1B2C3", "SENSOR-ESTEIRA-FIM") == (["OK"], ["DOCA:2"]))
check("doca de saida: OK sem comando", passo("04A1B2C3", "SENSOR-DOCA-SAIDA") == (["OK"], []))
check("produto expedido nao volta", passo("04A1B2C3", "SENSOR-DOCA-ENTRADA") == (["ERRO"], []))

# sem esteira conectada nao quebra
requests.post(API + "/produtos", data={"uid": "AA000001", "tipo_produto_id": 1})
passo("AA000001", "SENSOR-DOCA-ENTRADA")
check("sem --esteira: leitor recebe OK e nada quebra", passo("AA000001", "SENSOR-ESTEIRA-INICIO", esteira=False) == (["OK"], []))

# sensor ativo escolhido no site (a ponte nao manda o sensor)
requests.post(API + "/produtos", data={"uid": "AA000002", "tipo_produto_id": 4})   # TV 60 -> RUA 4
requests.post(API + "/sensor-ativo", data={"sensor": "SENSOR-DOCA-ENTRADA"})
passo("AA000002")
requests.post(API + "/sensor-ativo", data={"sensor": "SENSOR-ESTEIRA-INICIO"})
check("sensor ativo do site: esteira recebe RUA:4", passo("AA000002") == (["OK"], ["RUA:4"]))

# mensagens vindas da esteira
L, E = Fake(), Fake(["# debug qualquer", "ERRO"])
ponte.ler_esteira(E, L)
check("ERRO da esteira faz o leitor apitar", L.saida == ["ERRO"])

# site fora do ar
L = Fake()
ponte.tratar_linha("UID;AAAA", "http://127.0.0.1:9", None, L, Fake())
check("site fora do ar: leitor recebe ERRO", L.saida == ["ERRO"])

print("\nFalhas:", falhas)
raise SystemExit(1 if falhas else 0)
