"""
Ponte USB entre os Arduinos e o site.

  Arduino leitor (leitor_site.ino)  --USB-->  ponte.py  --HTTP-->  site (Flask + banco)
                                                 |
                                                 +--USB-->  Arduino da esteira

O site decide tudo. Quando a leitura exige uma acao da esteira, ele devolve o texto do comando
(ex.: "RUA:2" ou "DOCA:3") e a ponte so repassa esse texto, linha por linha, para a esteira.
Para mudar o texto dos comandos edite COMANDO_RUA / COMANDO_DOCA em regras.py.

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

BAUD = 9600  # igual nos sketches do leitor e da esteira


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


def tratar_linha(linha, api, sensor_fixo, ser_leitor, ser_esteira):
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
    if sensor_fixo:
        corpo["sensor"] = sensor_fixo

    try:
        r = requests.post(f"{api}/api/tag-lida", json=corpo, timeout=3)
        dados = r.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[site] sem resposta ({e}). O site esta rodando?")
        enviar(ser_leitor, "ERRO")
        return None

    print(f"[site] {'OK' if dados.get('ok') else 'ERRO'}: {dados.get('mensagem')}")
    enviar(ser_leitor, "OK" if dados.get("ok") else "ERRO")

    comando = dados.get("comando")
    if dados.get("ok") and comando:
        if ser_esteira:
            enviar(ser_esteira, comando)
            print(f"[esteira] {comando}")
        else:
            print(f"[esteira] (ponte iniciada sem --esteira: '{comando}' nao foi enviado)")
    return dados


def ler_esteira(ser_esteira, ser_leitor):
    """Mostra o que a esteira enviou. Se ela avisar ERRO, o leitor apita."""
    while ser_esteira.in_waiting:
        linha = ser_esteira.readline().decode(errors="ignore").strip()
        if not linha:
            continue
        print(f"[esteira] {linha}")
        if linha == "ERRO":
            enviar(ser_leitor, "ERRO")


def teste_manual(ser_esteira):
    """Qualquer linha digitada no terminal e enviada como esta para a esteira (ex.: RUA:2)."""
    while True:
        try:
            texto = input().strip()
        except EOFError:
            return
        if texto:
            enviar(ser_esteira, texto)
            print(f"[esteira] {texto} (teste manual)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true", help="lista as portas seriais e sai")
    ap.add_argument("--leitor", help="porta do Arduino leitor, ex.: COM3")
    ap.add_argument("--esteira", help="porta do Arduino da esteira, ex.: COM4 (opcional)")
    ap.add_argument("--api", default="http://127.0.0.1:5000", help="endereco do site")
    ap.add_argument("--sensor", help="forca um sensor do banco (ex.: SENSOR-ESTEIRA-INICIO); "
                                     "sem isso vale o sensor escolhido no site")
    a = ap.parse_args()

    if a.listar:
        return listar_portas()
    if not a.leitor:
        ap.error("informe --leitor COMx (use --listar para ver as portas)")

    ser_leitor = abrir(a.leitor, "o leitor")
    ser_esteira = abrir(a.esteira, "a esteira") if a.esteira else None
    if ser_esteira:
        print("Teste manual: digite um comando (ex.: RUA:2 ou DOCA:3) + Enter para enviar a esteira.")
        threading.Thread(target=teste_manual, args=(ser_esteira,), daemon=True).start()
    print("Ponte ativa. Aproxime uma tag. (Ctrl+C para sair)")

    try:
        while True:
            linha = ser_leitor.readline().decode(errors="ignore")
            if linha:
                tratar_linha(linha, a.api.rstrip("/"), a.sensor, ser_leitor, ser_esteira)
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
