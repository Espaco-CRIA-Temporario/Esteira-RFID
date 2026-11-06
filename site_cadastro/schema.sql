-- Banco de dados do armazem (SQLite). Para MySQL/PostgreSQL a estrutura e a mesma.

CREATE TABLE IF NOT EXISTS tipos_produto (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao   TEXT NOT NULL UNIQUE,          -- 'TV 45', 'TV 50'...
    polegadas   INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS destinos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL UNIQUE,          -- 'Destino 1'...
    rota_esteira INTEGER NOT NULL UNIQUE       -- numero que o codigo da esteira entende
);

CREATE TABLE IF NOT EXISTS docas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT NOT NULL UNIQUE,          -- 'ENT-1', 'SAI-1'...
    tipo        TEXT NOT NULL CHECK (tipo IN ('ENTRADA','SAIDA')),
    destino_id  INTEGER REFERENCES destinos(id) -- so as docas de saida tem destino
);

CREATE TABLE IF NOT EXISTS porta_palets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT NOT NULL UNIQUE,          -- 'PP-TV45-A'
    tipo_produto_id INTEGER NOT NULL REFERENCES tipos_produto(id)
);

-- Cada leitor RFID fisico (doca de entrada, palet ou doca de saida)
CREATE TABLE IF NOT EXISTS leitores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT NOT NULL UNIQUE,
    local       TEXT NOT NULL CHECK (local IN ('DOCA_ENTRADA','PALET','DOCA_SAIDA')),
    doca_id     INTEGER REFERENCES docas(id),
    palet_id    INTEGER REFERENCES porta_palets(id)
);

CREATE TABLE IF NOT EXISTS produtos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_uid     TEXT NOT NULL UNIQUE,          -- UID do cartao/tag RFID
    tipo_id     INTEGER NOT NULL REFERENCES tipos_produto(id),
    status      TEXT NOT NULL DEFAULT 'CADASTRADO'
                CHECK (status IN ('CADASTRADO','NA_DOCA','NO_PALET','DESTINO_DEFINIDO','ENTREGUE')),
    doca_entrada_id INTEGER REFERENCES docas(id),
    palet_id    INTEGER REFERENCES porta_palets(id),
    destino_id  INTEGER REFERENCES destinos(id),
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS eventos_leitura (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_uid     TEXT NOT NULL,
    produto_id  INTEGER REFERENCES produtos(id),
    leitor_id   INTEGER REFERENCES leitores(id),
    sucesso     INTEGER NOT NULL,
    resultado   TEXT NOT NULL,
    data_hora   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---- Integracao com o leitor fisico (ponte USB) ----

-- Configuracao do site. 'leitor_ativo' diz o que o leitor fisico esta fazendo agora:
--   'CADASTRO'  = so captura o UID para preencher o formulario de cadastro
--   'LEITOR-...' = age como aquele leitor (doca de entrada, palet ou doca de saida)
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
INSERT OR IGNORE INTO config(chave, valor) VALUES ('leitor_ativo', 'CADASTRO');

-- Ultima tag lida no modo CADASTRO (uma unica linha, id = 1)
CREATE TABLE IF NOT EXISTS ultima_leitura (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    seq       INTEGER NOT NULL,
    tag_uid   TEXT NOT NULL,
    data_hora TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
