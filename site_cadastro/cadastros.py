"""Tabelas que podem ser editadas pelo site (aba "Cadastros").

PARA ADICIONAR OU MUDAR UM CAMPO: mexa so no dicionario CADASTROS abaixo. As telas, o
formulario de "adicionar", a edicao e a exclusao saem sozinhos dessa descricao.

Tipos de campo:
    "texto"   caixa de texto
    "numero"  numero inteiro
    "ref"     escolhe uma linha de outra tabela:  "ref": ("tabela", "coluna_que_aparece")
    "opcoes"  lista fixa:                          "opcoes": {valor_gravado: "nome mostrado"}
Cada campo aceita "obrigatorio": False para permitir ficar em branco (padrao: obrigatorio).
"""
import sqlite3

from regras import LOCAIS_SENSOR, STATUS

CADASTROS = {
    "tipos": {
        "titulo": "Tipos de produto",
        "tabela": "tipos_produto",
        "ordem": "polegadas",
        "ajuda": "Os tipos de TV. Cada tipo precisa de uma rua (aba Ruas).",
        "campos": [
            {"coluna": "nome", "rotulo": "Nome", "tipo": "texto"},
            {"coluna": "polegadas", "rotulo": "Polegadas", "tipo": "numero"},
        ],
    },
    "ruas": {
        "titulo": "Ruas",
        "tabela": "ruas",
        "ordem": "numero",
        "ajuda": "Cada rua guarda um tipo de produto. O numero e o que a esteira entende (comando RUA:n).",
        "campos": [
            {"coluna": "codigo", "rotulo": "Nome da rua", "tipo": "texto"},
            {"coluna": "numero", "rotulo": "Numero na esteira", "tipo": "numero"},
            {"coluna": "tipo_produto_id", "rotulo": "Tipo de produto", "tipo": "ref", "ref": ("tipos_produto", "nome")},
            {"coluna": "porta_pallets", "rotulo": "Porta-pallets", "tipo": "numero"},
        ],
    },
    "docas": {
        "titulo": "Docas",
        "tabela": "docas",
        "ordem": "numero",
        "ajuda": "O numero e o que a esteira entende (comando DOCA:n).",
        "campos": [
            {"coluna": "codigo", "rotulo": "Nome da doca", "tipo": "texto"},
            {"coluna": "numero", "rotulo": "Numero na esteira", "tipo": "numero"},
        ],
    },
    "destinos": {
        "titulo": "Destinos finais",
        "tabela": "destinos",
        "ordem": "nome",
        "ajuda": "Cada destino sai do armazem por uma doca.",
        "campos": [
            {"coluna": "nome", "rotulo": "Destino", "tipo": "texto"},
            {"coluna": "doca_id", "rotulo": "Doca de saida", "tipo": "ref", "ref": ("docas", "codigo"), "obrigatorio": False},
        ],
    },
    "sensores": {
        "titulo": "Sensores",
        "tabela": "sensores",
        "ordem": "id",
        "ajuda": "O 'local' define o que a leitura significa. A doca e opcional (so confere se o produto saiu pela doca certa).",
        "campos": [
            {"coluna": "codigo", "rotulo": "Codigo", "tipo": "texto"},
            {"coluna": "local", "rotulo": "Local", "tipo": "opcoes", "opcoes": LOCAIS_SENSOR},
            {"coluna": "doca_id", "rotulo": "Doca do sensor", "tipo": "ref", "ref": ("docas", "codigo"), "obrigatorio": False},
        ],
    },
    "produtos": {
        "titulo": "Produtos (edicao direta)",
        "titulo_curto": "Produtos",
        "tabela": "produtos",
        "ordem": "id",
        "atualiza": "atualizado_em=datetime('now','localtime')",
        "ajuda": "Atencao: aqui as regras do fluxo NAO sao aplicadas. Serve para corrigir erros ou refazer um teste "
                 "(ex.: voltar o status para 'Cadastrado').",
        "campos": [
            {"coluna": "tag_uid", "rotulo": "UID da tag", "tipo": "texto"},
            {"coluna": "tipo_produto_id", "rotulo": "Tipo", "tipo": "ref", "ref": ("tipos_produto", "nome")},
            {"coluna": "status", "rotulo": "Status", "tipo": "opcoes", "opcoes": STATUS},
            {"coluna": "rua_id", "rotulo": "Rua", "tipo": "ref", "ref": ("ruas", "codigo"), "obrigatorio": False},
            {"coluna": "destino_id", "rotulo": "Destino", "tipo": "ref", "ref": ("destinos", "nome"), "obrigatorio": False},
        ],
    },
}

for _cfg in CADASTROS.values():
    for _c in _cfg["campos"]:
        _c.setdefault("obrigatorio", True)


# ---------------------------------------------------------------- consultas
def linhas(db, cfg):
    return db.execute(f"SELECT * FROM {cfg['tabela']} ORDER BY {cfg['ordem']}").fetchall()


def opcoes(db, cfg):
    """Para cada campo 'ref' ou 'opcoes': lista de (valor, nome) usada nos <select>."""
    resultado = {}
    for c in cfg["campos"]:
        if c["tipo"] == "ref":
            tabela, coluna = c["ref"]
            resultado[c["coluna"]] = [(r[0], r[1]) for r in db.execute(
                f"SELECT id, {coluna} FROM {tabela} ORDER BY {coluna}")]
        elif c["tipo"] == "opcoes":
            resultado[c["coluna"]] = list(c["opcoes"].items())
    return resultado


# ---------------------------------------------------------------- gravacao
def ler_formulario(cfg, form):
    """Converte o formulario em {coluna: valor}. Levanta ValueError com mensagem para o usuario."""
    valores = {}
    for c in cfg["campos"]:
        bruto = (form.get(c["coluna"]) or "").strip()
        if bruto == "":
            if c["obrigatorio"]:
                raise ValueError(f"Preencha o campo: {c['rotulo']}.")
            valores[c["coluna"]] = None
        elif c["tipo"] in ("numero", "ref"):
            try:
                valores[c["coluna"]] = int(bruto)
            except ValueError:
                raise ValueError(f"O campo '{c['rotulo']}' precisa ser um numero.") from None
        elif c["tipo"] == "opcoes":
            if bruto not in c["opcoes"]:
                raise ValueError(f"Valor invalido em: {c['rotulo']}.")
            valores[c["coluna"]] = bruto
        else:
            valores[c["coluna"]] = bruto
    return valores


def _erro_sqlite(e, acao):
    texto = str(e)
    if "UNIQUE" in texto:
        return "Ja existe um registro com esse valor (nome, numero ou UID repetido)."
    if "FOREIGN KEY" in texto:
        return ("Nao da para excluir: este registro e usado em outra tabela."
                if acao == "excluir" else "Valor invalido: o item escolhido nao existe.")
    return f"O banco recusou a alteracao: {texto}"


def salvar(db, cfg, valores, id=None):
    """Insere (id=None) ou atualiza. Retorna (ok, mensagem). Nomes de tabela/coluna vem da configuracao."""
    colunas = list(valores)
    try:
        if id is None:
            db.execute(f"INSERT INTO {cfg['tabela']} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
                       [valores[c] for c in colunas])
        else:
            sets = [f"{c}=?" for c in colunas] + ([cfg["atualiza"]] if cfg.get("atualiza") else [])
            db.execute(f"UPDATE {cfg['tabela']} SET {', '.join(sets)} WHERE id=?", [valores[c] for c in colunas] + [id])
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        return False, _erro_sqlite(e, "salvar")
    return True, "Adicionado." if id is None else "Salvo."


def excluir(db, cfg, id):
    try:
        db.execute(f"DELETE FROM {cfg['tabela']} WHERE id=?", (id,))
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        return False, _erro_sqlite(e, "excluir")
    return True, "Excluido."
