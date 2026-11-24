"""Apaga o banco e recria do zero (estrutura do schema.sql + dados do dados_iniciais.sql).

Uso (com o site fechado):   python resetar_banco.py
O banco atual nao e apagado de verdade: vira armazem_antigo_DATA.db.
"""
import os
import time

import banco


def main():
    if os.path.exists(banco.DB) and os.path.getsize(banco.DB) > 0:
        backup = os.path.join(os.path.dirname(banco.DB), "armazem_antigo_" + time.strftime("%Y%m%d-%H%M%S") + ".db")
        os.replace(banco.DB, backup)
        print("Banco antigo guardado em:", backup)
    banco.criar_banco(banco.DB)
    print("Banco novo criado em:", banco.DB)


if __name__ == "__main__":
    main()
