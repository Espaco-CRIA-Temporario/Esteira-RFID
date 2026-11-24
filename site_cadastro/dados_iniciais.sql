-- ============================================================================
--  DADOS INICIAIS: usados so quando o banco e criado (ou resetado).
--  Depois disso, edite os dados pela aba "Cadastros" do site.
-- ============================================================================

INSERT INTO tipos_produto (nome, polegadas) VALUES
    ('TV 45', 45),
    ('TV 50', 50),
    ('TV 55', 55),
    ('TV 60', 60);

-- 4 ruas, uma para cada tipo de produto, com 2 porta-pallets cada
INSERT INTO ruas (codigo, numero, tipo_produto_id, porta_pallets) VALUES
    ('RUA 1', 1, (SELECT id FROM tipos_produto WHERE nome = 'TV 45'), 2),
    ('RUA 2', 2, (SELECT id FROM tipos_produto WHERE nome = 'TV 50'), 2),
    ('RUA 3', 3, (SELECT id FROM tipos_produto WHERE nome = 'TV 55'), 2),
    ('RUA 4', 4, (SELECT id FROM tipos_produto WHERE nome = 'TV 60'), 2);

-- 4 docas (entrada e saida)
INSERT INTO docas (codigo, numero) VALUES
    ('DOCA 1', 1),
    ('DOCA 2', 2),
    ('DOCA 3', 3),
    ('DOCA 4', 4);

-- 4 destinos finais, cada um sai por uma doca
INSERT INTO destinos (nome, doca_id) VALUES
    ('Destino 1', (SELECT id FROM docas WHERE numero = 1)),
    ('Destino 2', (SELECT id FROM docas WHERE numero = 2)),
    ('Destino 3', (SELECT id FROM docas WHERE numero = 3)),
    ('Destino 4', (SELECT id FROM docas WHERE numero = 4));

-- 4 sensores: doca de entrada, inicio da esteira, fim da esteira, doca de saida
INSERT INTO sensores (codigo, local) VALUES
    ('SENSOR-DOCA-ENTRADA',   'DOCA_ENTRADA'),
    ('SENSOR-ESTEIRA-INICIO', 'ESTEIRA_INICIO'),
    ('SENSOR-ESTEIRA-FIM',    'ESTEIRA_FIM'),
    ('SENSOR-DOCA-SAIDA',     'DOCA_SAIDA');

INSERT INTO config (chave, valor) VALUES ('sensor_ativo', 'CADASTRO');
