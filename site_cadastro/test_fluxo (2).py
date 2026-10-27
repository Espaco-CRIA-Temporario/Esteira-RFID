"""
Ponte USB entre os Arduinos e o site.

  Arduino leitor (PN532)  --USB-->  ponte.py  --HTTP-->  site (Flask + banco)
                                       |
                                       +--USB-->  Arduino da esteira (recebe ROTA;n e MOTOR)

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

BAUD = 9600  # igual nos dois sketches (leitor_rfid.ino e esteira.ino)


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


def tratar_linha(linha, api, leitor_fixo, ser_leitor, ser_esteira):
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
    enviar(ser_leitor, "OK" if dados.get("ok") else "ERRO")

    if dados.get("ok") and dados.get("esteira") and ser_esteira:
        if dados.get("rota") is not None:
            enviar(ser_esteira, f"ROTA;{dados['rota']}")  # esteira.ino atual ignora; uso futuro
        enviar(ser_esteira, "MOTOR")
        print(f"[esteira] MOTOR (rota {dados.get('rota')})")
    return dados


def teste_manual(ser_esteira):
    """Digitar 'm' + Enter manda MOTOR para a esteira (para testar a ligacao)."""
    while True:
        try:
            if input().strip().lower() == "m":
                enviar(ser_esteira, "MOTOR")
                print("[esteira] MOTOR (teste manual)")
        except EOFError:
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true", help="lista as portas seriais e sai")
    ap.add_argument("--leitor", help="porta do Arduino leitor, ex.: COM3")
    ap.add_argument("--esteira", help="porta do Arduino da esteira, ex.: COM4 (opcional)")
    ap.add_argument("--api", default="http://127.0.0.1:5000", help="endereco do site")
    ap.add_argument("--como", help="forca um leitor do banco (ex.: LEITOR-ENT-1); "
                                   "sem isso vale o leitor escolhido no site")
    a = ap.parse_args()

    if a.listar:
        return listar_portas()
    if not a.leitor:
        ap.error("informe --leitor COMx (use --listar para ver as portas)")

    ser_leitor = abrir(a.leitor, "o leitor")
    ser_esteira = abrir(a.esteira, "a esteira") if a.esteira else None
    print("Ponte ativa. Aproxime uma tag. (Ctrl+C para sair)")
    if ser_esteira:
        print("Digite 'm' + Enter para testar o motor da esteira.")
        threading.Thread(target=teste_manual, args=(ser_esteira,), daemon=True).start()

    try:
        while True:
            linha = ser_leitor.readline().decode(errors="ignore")
            if linha:
                tratar_linha(linha, a.api.rstrip("/"), a.como, ser_leitor, ser_esteira)
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        ser_leitor.close()
        if ser_esteira:
            ser_esteira.close()


if __name__ == "__main__":
    main()
