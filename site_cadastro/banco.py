"""Banco de dados (SQLite): conexao, criacao das tabelas, dados iniciais e consultas simples."""
import os
import sqlite3

from flask import g

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("ARMAZEM_DB", os.path.join(BASE, "armazem.db"))


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


def seed(db):
    for pol in (45, 50, 55, 60):
        db.execute("INSERT INTO tipos_produto(descricao, polegadas) VALUES (?,?)", (f"TV {pol}", pol))
    for n in range(1, 5):
        db.execute("INSERT INTO destinos(nome, rota_esteira) VALUES (?,?)", (f"Destino {n}", n))
    for n in range(1, 5):
        db.execute("INSERT INTO docas(codigo, tipo) VALUES (?, 'ENTRADA')", (f"ENT-{n}",))
    for n in range(1, 5):
        db.execute("INSERT INTO docas(codigo, tipo, destino_id) VALUES (?, 'SAIDA', ?)", (f"SAI-{n}", n))
    for t in db.execute("SELECT id, polegadas FROM tipos_produto").fetchall():
        for letra in ("A", "B"):
            db.execute(
                "INSERT INTO porta_palets(codigo, tipo_produto_id) VALUES (?,?)",
                (f"PP-TV{t['polegadas']}-{letra}", t["id"]),
            )
    for d in db.execute("SELECT id, codigo, tipo FROM docas").fetchall():
        local = "DOCA_ENTRADA" if d["tipo"] == "ENTRADA" else "DOCA_SAIDA"
        db.execute(
            "INSERT INTO leitores(codigo, local, doca_id) VALUES (?,?,?)",
            (f"LEITOR-{d['codigo']}", local, d["id"]),
        )
    for p in db.execute("SELECT id, codigo FROM porta_palets").fetchall():
        db.execute(
            "INSERT INTO leitores(codigo, local, palet_id) VALUES (?, 'PALET', ?)",
            (f"LEITOR-{p['codigo']}", p["id"]),
        )


def init_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    if db.execute("SELECT COUNT(*) FROM tipos_produto").fetchone()[0] == 0:
        seed(db)
    db.commit()
    db.close()


def normalizar_uid(uid):
    return (uid or "").strip().upper().replace(" ", "")


def leitor_ativo(db):
    """O que o leitor fisico esta fazendo agora: 'CADASTRO', 'ESTEIRA' ou o codigo de um leitor."""
    return db.execute("SELECT valor FROM config WHERE chave='leitor_ativo'").fetchone()[0]


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
