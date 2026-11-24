# Site do armazém (versão nova: esteira única, 4 ruas, 4 docas)

## O fluxo de um produto
```
Site cadastra a TV (UID da tag + tipo)                              CADASTRADO
  -> sensor da DOCA DE ENTRADA                                      NA_DOCA
  -> sensor do INÍCIO DA ESTEIRA identifica o tipo e desvia
     para a rua certa (comando RUA:n)                               NA_RUA
     (dentro da rua o trabalho é manual: só se controla a rua)
  -> no site, define-se o DESTINO (só depois de estar na rua)       DESTINO_DEFINIDO
  -> sensor do FIM DA ESTEIRA lê o destino e desvia para a
     doca de saída certa (comando DOCA:n)                           NA_ESTEIRA
  -> sensor da DOCA DE SAÍDA confirma que saiu do armazém           EXPEDIDO
```

## Como rodar (PowerShell, dentro da pasta `site_cadastro`)
```
python -m pip install -r requirements.txt
python app.py
```
Abra http://localhost:5000. O banco `armazem.db` é criado sozinho na primeira vez.
Se existir um `armazem.db` do formato antigo, ele é guardado como `armazem_antigo_DATA.db` e um banco novo é criado.

## Páginas do site
| Página | Para quê |
|---|---|
| **Painel** | Quantos produtos em cada etapa, escolher o que o leitor físico está fazendo, simular leituras sem Arduino |
| **Produtos** | Cadastrar (a tag lida preenche o UID sozinha) e definir o destino de cada produto |
| **Armazém** | O que há em cada rua e o movimento de cada doca |
| **Histórico** | Todas as leituras, com acerto/erro e o comando enviado à esteira |
| **Cadastros** | **Editar o banco**: tipos de TV, ruas, docas, destinos, sensores e até os produtos |
| **Banco** | Todas as tabelas do banco, só para olhar |

## Como editar cada coisa
| Quero mudar... | Onde |
|---|---|
| Tipos de TV, ruas, docas, destinos, sensores | Site, aba **Cadastros** (adicionar, salvar, excluir) |
| Corrigir um produto ou refazer um teste (voltar o status) | Site, **Cadastros > Produtos** |
| Os dados iniciais de um banco novo | `dados_iniciais.sql` e depois `python resetar_banco.py` |
| A estrutura das tabelas | `schema.sql` + aumentar `VERSAO_SCHEMA` em `banco.py` (o banco antigo vira backup) |
| Quais campos aparecem na aba Cadastros | `cadastros.py` (dicionário `CADASTROS`) |
| As regras do fluxo, nomes dos status, texto dos comandos da esteira | `regras.py` (bloco "AJUSTES FÁCEIS" no começo) |
| Cores, fontes, tamanhos | `static/estilo.css` (bloco `:root` no começo) |
| O texto e o layout das páginas | `templates/*.html` (`base.html` tem o menu) |
| As rotas e a API | `app.py` |

## Arquivos
```
site_cadastro/
  app.py                 rotas do site e da API
  regras.py              regras do fluxo (o que cada sensor significa)
  banco.py               conexão e criação do banco
  cadastros.py           descrição das tabelas editáveis (aba Cadastros)
  schema.sql             estrutura das tabelas
  dados_iniciais.sql     dados de um banco novo
  resetar_banco.py       recria o banco do zero (guarda o antigo)
  ponte.py               liga os Arduinos ao site
  templates/             páginas HTML (base.html = menu e layout)
  static/estilo.css      visual    static/app.js  pequenos comportamentos
  test_fluxo.py          testa site, regras e banco
  test_ponte.py          testa a ponte com Arduino simulado
```
A pasta `templates` e a pasta `static` precisam ficar ao lado do `app.py`.

## Ligar os Arduinos (ponte USB)
```
[Uno leitor + PN532] --USB--\
                             notebook: site (app.py) + ponte (ponte.py)
[Uno esteira]        --USB--/
```
1. Grave `structure/leitor_site/leitor_site.ino` no Uno do leitor (envia `UID;XXXXXXXX`). **Sem fios TX/RX entre os Unos.**
2. `python ponte.py --listar` mostra as portas. Com o site rodando, em outro terminal:
```
python ponte.py --leitor COM3 --esteira COM4
```
3. No **Painel**, escolha o que o leitor está fazendo (`CADASTRO` ou um dos 4 sensores). Com um leitor só, troque o sensor a cada etapa. Com um leitor por sensor, use `--sensor SENSOR-ESTEIRA-INICIO` em cada ponte.

**Comandos para a esteira.** O site responde às leituras com o texto do comando e a ponte só o repassa:
`RUA:n` (início da esteira: desviar para a rua n) e `DOCA:n` (fim da esteira: desviar para a doca n).
Os números vêm de **Cadastros > Ruas / Docas**. O `esteira.ino` atual da equipe ainda entende `CAIXA:n`:
ele precisa ser adaptado, ou ajuste `COMANDO_RUA` e `COMANDO_DOCA` em `regras.py` para o texto que ele entende.
Para testar a esteira sem site, com a ponte rodando digite um comando (ex.: `RUA:2`) e Enter.

## API (para a ponte ou para o código da esteira)
- `POST /api/tag-lida` com `{"uid": "04A1B2C3"}` (opcional `"sensor": "SENSOR-..."`) devolve `{ok, mensagem, comando}`.
- `GET /api/produtos/<uid>` devolve status, tipo, rua e destino de uma tag.
- `GET /api/produtos`, `GET /api/ultima-leitura`.

## Testes sem hardware
```
python test_fluxo.py
python test_ponte.py
```
Os dois terminam com `Falhas: 0`.

## Suposições feitas (confirmar com a logística)
- "Chegou na rua" = o sensor do início da esteira identificou o tipo e desviou. Não há sensor dentro das ruas.
- As 4 docas servem para entrada e saída; cada destino sai por uma doca (editável em Cadastros > Destinos).
- Cada rua guarda um tipo de produto; os 2 porta-pallets são só informativos (o controle é por rua).
- Depois de `EXPEDIDO` o produto não volta a entrar. Para refazer um teste, use Cadastros > Produtos.
