# Ligação: Arduino (leitor) + esteira + site

```
[Uno 1 + PN532] --USB--\
                         notebook: site (app.py) + ponte (ponte.py)
[Uno 2 + motor] --USB--/
```

## 1. Antes de ligar
- **Retire qualquer fio entre os pinos 0/1 (TX/RX) dos dois Unos.** Com os dois por USB, esses pinos
  conflitam com a comunicação USB. A ponte substitui essa ligação.
- Mantenha o PN532 em modo SPI (chaves DIP: SEL0 = OFF, SEL1 = ON).

## 2. Gravar os Arduinos (IDE do Arduino)
- Uno do leitor: abra `leitor_rfid/leitor_rfid.ino` (biblioteca Adafruit PN532) e envie.
- Uno da esteira: o `esteira.ino` que você já tem (ele só entende a linha `MOTOR`).
- Depois **feche o Monitor Serial** da IDE: ele ocupa a porta e a ponte não consegue abrir.

## 3. Instalar e rodar (PowerShell, nesta pasta)
```
python -m pip install -r requirements.txt
python ponte.py --listar
```
Aparecem as portas, ex.: `COM3` e `COM4`. Descubra qual é qual desconectando um cabo e rodando de novo.

Abra **dois** PowerShell na pasta:
```
# janela 1: o site
python app.py

# janela 2: a ponte
python ponte.py --leitor COM3 --esteira COM4
```
Abra http://localhost:5000.

## 4. Como usar
1. **Cadastrar:** no site, "Leitor físico" fica em `CADASTRO`. Aproxime a tag: o UID aparece sozinho no
   campo, escolha o tipo da TV e clique em Cadastrar. O leitor dá bipe duplo (OK) ou 3 bipes (erro).
2. **Operar:** troque o "Leitor físico" no site para `LEITOR-ENT-1`, `LEITOR-PP-TV50-A`, `LEITOR-SAI-3`...
   e aproxime a tag. O site aplica as regras (palet errado, destino só após o palet etc.).
   Também dá para forçar sem mexer no site: `python ponte.py --leitor COM3 --como LEITOR-ENT-1`.
3. **Esteira:** quando um produto passa com sucesso pela doca de saída, a ponte envia `ROTA;n` e `MOTOR`
   para a esteira. Para testar só o motor: com a ponte rodando, digite `m` + Enter.
   (Para mudar em que ponto a esteira anda, altere `ESTEIRA_ACIONA_EM` no início do `app.py`.)

## Observações
- O `esteira.ino` atual só liga o motor; ele ignora a linha `ROTA;n`. Quando a esteira ganhar os
  desvios, basta ela tratar essa linha, sem mexer na ponte nem no site.
- O banco `armazem.db` existente continua valendo: as tabelas novas são criadas sozinhas.
- Para conferir o site sem hardware: `python test_fluxo.py`.
