-- ============================================================================
--  ESTRUTURA DO BANCO (SQLite)
--  Para mudar a estrutura: edite este arquivo, aumente VERSAO_SCHEMA em banco.py
--  (ou rode "python resetar_banco.py"). O banco antigo vira um arquivo de backup.
--  Para mudar so os DADOS (tipos, ruas, docas...): use a aba "Cadastros" do site
--  ou edite dados_iniciais.sql e rode "python resetar_banco.py".
-- ============================================================================

-- Tipos de produto vendidos: TV 45, TV 50...
CREATE TABLE tipos_produto (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nome      TEXT    NOT NULL UNIQUE,            -- 'TV 50'
    polegadas INTEGER NOT NULL UNIQUE
);

-- Ruas do armazem. Cada rua guarda UM tipo de produto e tem 2 porta-pallets.
-- O controle e por rua (dentro dela o trabalho e manual).
CREATE TABLE ruas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT    NOT NULL UNIQUE,      -- 'RUA 1'
    numero          INTEGER NOT NULL UNIQUE,      -- numero que a esteira entende (RUA:1)
    tipo_produto_id INTEGER NOT NULL UNIQUE REFERENCES tipos_produto(id),
    porta_pallets   INTEGER NOT NULL DEFAULT 2
);

-- As 4 docas (usadas para entrada e para saida)
CREATE TABLE docas (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT    NOT NULL UNIQUE,               -- 'DOCA 1'
    numero INTEGER NOT NULL UNIQUE                -- numero que a esteira entende (DOCA:1)
);

-- Destinos finais. Cada destino sai por uma doca.
CREATE TABLE destinos (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT    NOT NULL UNIQUE,              -- 'Destino 1'
    doca_id INTEGER REFERENCES docas(id)          -- doca por onde o produto sai
);

-- Sensores RFID. O campo "local" diz o que a leitura significa (veja regras.py).
CREATE TABLE sensores (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo  TEXT NOT NULL UNIQUE,                 -- 'SENSOR-ESTEIRA-INICIO'
    local   TEXT NOT NULL CHECK (local IN ('DOCA_ENTRADA','ESTEIRA_INICIO','ESTEIRA_FIM','DOCA_SAIDA')),
    doca_id INTEGER REFERENCES docas(id)          -- opcional: doca em que o sensor fica
);

-- Os produtos (uma linha por TV com tag)
CREATE TABLE produtos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_uid         TEXT    NOT NULL UNIQUE,      -- UID da tag RFID
    tipo_produto_id INTEGER NOT NULL REFERENCES tipos_produto(id),
    status          TEXT    NOT NULL DEFAULT 'CADASTRADO',   -- veja STATUS em regras.py
    doca_entrada_id INTEGER REFERENCES docas(id),
    rua_id          INTEGER REFERENCES ruas(id),
    destino_id      INTEGER REFERENCES destinos(id),
    criado_em       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Historico de todas as leituras (acertos e erros)
CREATE TABLE eventos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_uid    TEXT NOT NULL,
    produto_id INTEGER REFERENCES produtos(id) ON DELETE SET NULL,
    sensor_id  INTEGER REFERENCES sensores(id) ON DELETE SET NULL,
    sucesso    INTEGER NOT NULL,
    resultado  TEXT NOT NULL,
    comando    TEXT,                              -- comando enviado a esteira, se houve
    data_hora  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Configuracoes do site. 'sensor_ativo' = o que o leitor fisico esta fazendo agora:
-- 'CADASTRO' (so captura o UID) ou o codigo de um sensor.
CREATE TABLE config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Ultima tag lida no modo CADASTRO (uma unica linha, id = 1)
CREATE TABLE ultima_leitura (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    seq       INTEGER NOT NULL,
    tag_uid   TEXT NOT NULL,
    data_hora TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
