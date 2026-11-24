"""Banco de dados (SQLite): conexao, criacao das tabelas e consultas simples.

Para mudar DADOS (tipos, ruas, docas...) use a aba "Cadastros" do site.
Para mudar a ESTRUTURA edite schema.sql e aumente VERSAO_SCHEMA abaixo.
"""
import os
import sqlite3
import time

from flask import g

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("ARMAZEM_DB", os.path.join(BASE, "armazem.db"))

# Aumente este numero sempre que mudar o schema.sql. Se o banco existente tiver outra
# versao, ele e guardado como backup (armazem_antigo_DATA.db) e um banco novo e criado.
VERSAO_SCHEMA = 2


def _ler(nome):
    with open(os.path.join(BASE, nome), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- conexao
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def fechar_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_app(app):
    """Faz o Flask fechar a conexao no fim de cada requisicao."""
    app.teardown_appcontext(fechar_db)


# ---------------------------------------------------------------- criacao
def criar_banco(caminho):
    """Cria um banco novo (estrutura + dados iniciais) no arquivo indicado."""
    db = sqlite3.connect(caminho)
    db.executescript(_ler("schema.sql"))
    db.executescript(_ler("dados_iniciais.sql"))
    db.execute(f"PRAGMA user_version = {VERSAO_SCHEMA}")
    db.commit()
    db.close()


def init_db(caminho=None):
    """Garante um banco pronto. Retorna o caminho do backup, se o banco antigo foi guardado."""
    caminho = caminho or DB
    backup = None
    if os.path.exists(caminho) and os.path.getsize(caminho) > 0:
        con = sqlite3.connect(caminho)
        versao = con.execute("PRAGMA user_version").fetchone()[0]
        con.close()
        if versao == VERSAO_SCHEMA:
            return None
        backup = os.path.join(os.path.dirname(caminho), "armazem_antigo_" + time.strftime("%Y%m%d-%H%M%S") + ".db")
        os.replace(caminho, backup)
    criar_banco(caminho)
    return backup


# ---------------------------------------------------------------- consultas
def normalizar_uid(uid):
    return (uid or "").strip().upper().replace(" ", "")


def sensor_ativo(db):
    """O que o leitor fisico esta fazendo agora: 'CADASTRO' ou o codigo de um sensor."""
    r = db.execute("SELECT valor FROM config WHERE chave='sensor_ativo'").fetchone()
    return r[0] if r else "CADASTRO"


def tabelas(db):
    """Todas as tabelas com colunas, total e as 200 linhas mais recentes (para a pagina /banco)."""
    nomes = [r["name"] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    dados = []
    for nome in nomes:  # nomes vindos do proprio banco, nao do usuario
        cur = db.execute(f'SELECT * FROM "{nome}" ORDER BY 1 DESC LIMIT 200')
        colunas = [d[0] for d in cur.description]
        total = db.execute(f'SELECT COUNT(*) FROM "{nome}"').fetchone()[0]
        dados.append({"nome": nome, "colunas": colunas, "linhas": cur.fetchall(), "total": total})
    return dados
