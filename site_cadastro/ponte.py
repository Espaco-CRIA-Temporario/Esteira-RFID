"""
Ponte USB entre os Arduinos e o site.

  Arduino leitor (leitor_site.ino)  --USB-->  ponte.py  --HTTP-->  site (Flask + banco)
                                                 |
                                                 +--USB-->  Arduino da esteira (esteira.ino)

Protocolo da esteira (o mesmo do esteira.ino do projeto):
    RESET       limpa a fila e desliga a esteira (enviado ao iniciar a ponte)
    CAIXA:n     nova caixa na fila, destino = doca n (1..3)
    ERRO        (a esteira envia) viu uma caixa sem destino

Uso:
    python ponte.py --listar                      # mostra as portas COM disponiveis
    python ponte.py --leitor COM3                 # so o leitor (cadastro de produtos)
    python ponte.py --leitor COM3 --esteira COM4  # leitor + esteira
"""
import argparse
import sys
import threading
import time

import requests
import serial
from serial.tools import list_ports

BAUD = 9600          # igual nos sketches do leitor e da esteira
DOCAS_ESTEIRA = 3    # a esteira atual tem 3 docas (sensores + servos)


def listar_portas():
    portas = list(list_ports.comports())
    if not portas:
        print("Nenhuma porta serial encontrada. Confira os cabos USB.")
    for p in portas:
        print(f"{p.device}  -  {p.description}")


def abrir(porta, nome):
    try:
        s = serial.Serial(porta, BAUD, timeout=0.2)
    except serial.SerialException as e:
        sys.exit(f"Nao consegui abrir {nome} em {porta}: {e}\n"
                 "Feche o Monitor Serial da IDE do Arduino (ele ocupa a porta) e tente de novo.")
    time.sleep(2)  # o Uno reinicia quando a porta e aberta
    s.reset_input_buffer()
    return s


def enviar(ser, texto):
    ser.write((texto + "\n").encode())


def tratar_linha(linha, api, leitor_fixo, ser_leitor, ser_esteira, docas=DOCAS_ESTEIRA):
    """Processa uma linha vinda do Arduino leitor. Retorna a resposta da API (ou None)."""
    linha = linha.strip()
    if not linha:
        return None
    if not linha.startswith("UID;"):
        print(f"[leitor] {linha}")
        return None

    uid = linha[4:].strip().upper()
    print(f"[tag] {uid}")

    corpo = {"uid": uid}
    if leitor_fixo:
        corpo["leitor"] = leitor_fixo

    try:
        r = requests.post(f"{api}/api/tag-lida", json=corpo, timeout=3)
        dados = r.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[site] sem resposta ({e}). O site esta rodando?")
        enviar(ser_leitor, "ERRO")
        return None

    print(f"[site] {'OK' if dados.get('ok') else 'ERRO'}: {dados.get('mensagem')}")
    resposta_ok = bool(dados.get("ok"))

    if resposta_ok and dados.get("esteira"):
        rota = dados.get("rota")
        if not ser_esteira:
            print("[esteira] (ponte iniciada sem --esteira: nada enviado)")
        elif rota is None or not (1 <= int(rota) <= docas):
            print(f"[esteira] destino {rota} nao existe na esteira (ela tem {docas} docas). Nada enviado.")
            resposta_ok = False
        else:
            enviar(ser_esteira, f"CAIXA:{int(rota)}")
            print(f"[esteira] CAIXA:{int(rota)}")

    enviar(ser_leitor, "OK" if resposta_ok else "ERRO")
    return dados


def ler_esteira(ser_esteira, ser_leitor):
    """Mostra o que a esteira enviou. Se ela viu uma caixa sem destino (ERRO), avisa o leitor."""
    while ser_esteira.in_waiting:
        linha = ser_esteira.readline().decode(errors="ignore").strip()
        if not linha:
            continue
        print(f"[esteira] {linha}")
        if linha == "ERRO":
            enviar(ser_leitor, "ERRO")   # o leitor apita


def teste_manual(ser_esteira):
    """Digitar 1, 2 ou 3 + Enter manda CAIXA:n para a esteira; 'r' manda RESET."""
    while True:
        try:
            cmd = input().strip().lower()
        except EOFError:
            return
        if cmd in ("1", "2", "3"):
            enviar(ser_esteira, f"CAIXA:{cmd}")
            print(f"[esteira] CAIXA:{cmd} (teste manual)")
        elif cmd == "r":
            enviar(ser_esteira, "RESET")
            print("[esteira] RESET (teste manual)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true", help="lista as portas seriais e sai")
    ap.add_argument("--leitor", help="porta do Arduino leitor, ex.: COM3")
    ap.add_argument("--esteira", help="porta do Arduino da esteira, ex.: COM4 (opcional)")
    ap.add_argument("--docas", type=int, default=DOCAS_ESTEIRA, help="quantas docas a esteira tem (padrao 3)")
    ap.add_argument("--api", default="http://127.0.0.1:5000", help="endereco do site")
    ap.add_argument("--como", help="forca um leitor do banco (ex.: LEITOR-ENT-1 ou ESTEIRA); "
                                   "sem isso vale o leitor escolhido no site")
    a = ap.parse_args()

    if a.listar:
        return listar_portas()
    if not a.leitor:
        ap.error("informe --leitor COMx (use --listar para ver as portas)")

    ser_leitor = abrir(a.leitor, "o leitor")
    ser_esteira = abrir(a.esteira, "a esteira") if a.esteira else None
    if ser_esteira:
        enviar(ser_esteira, "RESET")   # esteira comeca com a fila vazia
        print("Esteira: fila limpa (RESET).")
        print("Teste manual: digite 1, 2 ou 3 + Enter para mandar uma caixa; 'r' + Enter para RESET.")
        threading.Thread(target=teste_manual, args=(ser_esteira,), daemon=True).start()
    print("Ponte ativa. Aproxime uma tag. (Ctrl+C para sair)")

    try:
        while True:
            linha = ser_leitor.readline().decode(errors="ignore")
            if linha:
                tratar_linha(linha, a.api.rstrip("/"), a.como, ser_leitor, ser_esteira, a.docas)
            if ser_esteira:
                ler_esteira(ser_esteira, ser_leitor)
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        ser_leitor.close()
        if ser_esteira:
            ser_esteira.close()


if __name__ == "__main__":
    main()
