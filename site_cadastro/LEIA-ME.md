# Site + leitor + esteira

Existem dois jeitos de usar o projeto. **Não misture os dois ao mesmo tempo.**

| | Jeito A: direto (sem site) | Jeito B: com o site (este LEIA-ME) |
|---|---|---|
| Leitor | `structure/leitor_rfid/leitor_rfid.ino` | `structure/leitor_site/leitor_site.ino` |
| Esteira | `structure/esteira/esteira.ino` | `structure/esteira/esteira.ino` (o mesmo) |
| Ligação dos Unos | fio TX/RX entre eles | **USB no notebook, sem fio TX/RX** |
| Destino da caixa | gravado no adesivo ("DOCA n") | definido no site, depois de a caixa chegar ao palet |

## Jeito B: como ligar

```
[Uno leitor  + PN532] --USB--\
                              notebook: site (app.py) + ponte (ponte.py)
[Uno esteira + motor ] --USB--/
```

1. **Retire os fios TX/RX (pinos 0 e 1) entre os dois Unos**, e o fio de reset, se houver. Com USB, a ponte faz esse papel.
2. Grave o `leitor_site.ino` no Uno do leitor e o `esteira.ino` no Uno da esteira. Ao gravar, o pino 0 (RX) do Uno da esteira deve estar sem fio. Depois **feche o Monitor Serial** da IDE.
3. Na pasta `site_cadastro` (PowerShell):
```
python -m pip install -r requirements.txt
python ponte.py --listar
```
Aparecem as portas (ex.: `COM3`, `COM4`). Descubra qual é qual desconectando um cabo e listando de novo.

4. Abra **dois** PowerShell nessa pasta:
```
# janela 1: o site
python app.py

# janela 2: a ponte
python ponte.py --leitor COM3 --esteira COM4
```
Abra http://localhost:5000.

## Como usar
1. **Cadastrar:** no site, o "Leitor físico" fica em `CADASTRO`. Aproxime a tag: o UID aparece no campo. Escolha o tipo da TV e clique em Cadastrar.
2. **Entrada e palet:** troque o "Leitor físico" para `LEITOR-ENT-1`, depois para o palet do tipo certo (`LEITOR-PP-TV50-A`...), aproximando a tag a cada troca.
3. **Destino:** defina o destino do produto na tabela do site (só aparece depois de ele chegar ao palet).
4. **Esteira:** troque o "Leitor físico" para `ESTEIRA` e aproxime a tag. O site libera o produto e a ponte envia `CAIXA:n` para a esteira, que leva a caixa até a doca n.

A ponte também envia `RESET` à esteira quando inicia, para ela começar com a fila vazia. Se a esteira vir uma caixa sem destino, ela manda `ERRO` e o leitor apita.

## Teste manual da esteira (sem site)
Com a ponte rodando, digite `1`, `2` ou `3` + Enter para mandar `CAIXA:n`, ou `r` + Enter para `RESET`.

## Limites atuais
- A esteira tem **3 docas**. O site tem 4 destinos; o Destino 4 é recusado na etapa `ESTEIRA` (ajuste `ESTEIRA_DOCAS` no `app.py` e `--docas` na ponte quando houver a 4ª).
- O banco `armazem.db` é criado sozinho na primeira execução e **não deve ir para o GitHub**.

## Testes sem hardware
```
python test_fluxo.py     # regras do site
python test_ponte.py     # ponte com serial simulada
```
Os dois terminam com `Falhas: 0`.
