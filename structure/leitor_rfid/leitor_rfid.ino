include <SPI.h>
#include <Adafruit_PN532.h>
/*
  LEITOR RFID - Arduino do leitor (PN532 em SPI + buzzer)

// ===== CONFIGURACOES =====
#define SS_PIN 10
#define BUZZER 8
  Ligações:
    PN532: SCK=13  MISO=12  MOSI=11  SS=10  VCC=5V  GND=GND
           chaves DIP: SEL0 = OFF, SEL1 = ON (modo SPI)
    Buzzer ATIVO: pino 8 e GND
    Serial: TX (pino 1) -> RX (pino 0) da esteira
            RX (pino 0) <- TX (pino 1) da esteira
            GND comum entre as duas placas

// 0 = GRAVAR | 1 = LER
int funcao = 1;
  Biblioteca necessária: Adafruit PN532

// Bloco de dados do setor 1 (evita o setor 0 e os blocos de trailer 3, 7, 11...)
uint8_t blocoTipo = 4;
  Modos (constante FUNCAO):
    0 = GRAVAR  -> grava "DOCA n" no bloco 4 do adesivo (n = DOCA_GRAVAR)
    1 = OPERAR  -> lê o adesivo e manda a caixa para a esteira

// Chave padrao A do MIFARE Classic
uint8_t chaveA[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  Protocolo serial (9600, linhas terminadas em \n):
    envia:   RESET        ao ligar, para a esteira limpar a fila
             CAIXA:n      leitura válida, caixa com destino na doca n (1..3)
             # texto      depuração (a esteira ignora)
    recebe:  ERRO         a esteira viu uma caixa sem destino

Adafruit_PN532 nfc(SS_PIN);
  Bipes:
    1 bipe curto   leitura válida (ou gravação ok)
    3 bipes curtos adesivo inválido / erro de leitura ou gravação / PN532 fora
    3 bipes longos a esteira detectou caixa sem destino

uint8_t uid[7];
uint8_t uidLength;
uint8_t dados[16];
  IMPORTANTE: ao fazer upload, desconecte o fio do pino 0 (RX).
*/

// ===== RESET POR CODIGO =====
// Reinicia o PN532 por software. Retorna a versao do firmware (0 = falhou)
uint32_t reiniciarPN532() {
  nfc.begin();
#include <SPI.h>
#include <Adafruit_PN532.h>

  uint32_t versao = nfc.getFirmwareVersion();
  if (!versao) return 0;
// ===================== CONFIGURAÇÃO =====================
const uint8_t FUNCAO      = 1;   // 0 = gravar adesivo, 1 = operar
const uint8_t DOCA_GRAVAR = 1;   // usado só no modo 0 (1, 2 ou 3)
const bool    DEBUG       = false;

  nfc.SAMConfig();
  nfc.setPassiveActivationRetries(0xFF);
  return versao;
}
#define SS_PIN 10
#define BUZZER 8

// Manda o comando "RESET" pelo TX (pino 1) para o RX (pino 0) do Arduino do motor.
// Ele reinicia o motor e o sensor.
void resetarArduinoMotor() {
  Serial.println(F("RESET"));
  delay(100);
}
const uint8_t BLOCO = 4;   // bloco de dados do MIFARE Classic (setor 1)

// Manda o comando "MOTOR" para o Arduino do motor comecar a girar
void enviarComandoMotor() {
  Serial.println(F("MOTOR"));
  Serial.println(F("Comando enviado ao motor."));
}
const unsigned long ATRASO_LEITURA_VALIDA_MS = 3000;  // ignora novas leituras após uma válida
const unsigned long ATRASO_ERRO_MS           = 1500;  // evita apitar sem parar no mesmo adesivo
const unsigned long VERIFICA_PN532_MS        = 15000; // confere se o PN532 continua respondendo
// ========================================================

// ===== SEPARADORES =====
void linha(char c = '-') {
  for (uint8_t i = 0; i < 40; i++) Serial.print(c);
  Serial.println();
}

void titulo(const __FlashStringHelper *texto) {
  Serial.println();
  linha('=');
  Serial.println(texto);
  linha('=');
}
static_assert(DOCA_GRAVAR >= 1 && DOCA_GRAVAR <= 3, "DOCA_GRAVAR deve ser 1, 2 ou 3");

// ===== BUZZER =====
void bip(int duracao = 150) {
  digitalWrite(BUZZER, HIGH);
  delay(duracao);
  digitalWrite(BUZZER, LOW);
}
Adafruit_PN532 nfc(SS_PIN);

void bipDuplo() {
  bip(120);
  delay(100);
  bip(120);
}
bool pn532Ok = false;
unsigned long tUltimaTentativa = 0;
unsigned long tVerifica = 0;

// Som de erro: 3 bipes curtos e rapidos
void bipErro() {
  for (int i = 0; i < 3; i++) {
    bip(80);
    delay(80);
  }
}
// atraso sem travar (usa millis)
unsigned long tAtraso = 0;
unsigned long atrasoMs = 0;

// ===== FUNCOES AUXILIARES =====
void esperarCartao() {
  Serial.println(F("Aguardando cartao..."));
// bipes sem travar
uint8_t bipesRestantes = 0;
bool buzzerLigado = false;
unsigned long tBipe = 0;
unsigned int durBipe = 100, pausaBipe = 100;

  while (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 500)) {
    // fica aqui em silencio
  }
// linha recebida da esteira
char linhaRx[16];
uint8_t posRx = 0;

  Serial.println(F("Cartao detectado!"));
  bip();
// ---------------------- utilidades ----------------------
void depurar(const __FlashStringHelper* msg) {
  if (!DEBUG) return;
  Serial.print(F("# "));
  Serial.println(msg);
}

void esperarRetirada() {
  Serial.println(F("Retire o cartao..."));
  delay(300);

  uint8_t uidTmp[7];
  uint8_t lenTmp;

  while (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uidTmp, &lenTmp, 300)) {
    delay(100);
  }
  delay(300);
void definirAtraso(unsigned long ms) {
  tAtraso = millis();
  atrasoMs = ms;
}

bool autenticarBloco() {
  if (uidLength != 4) {
    Serial.println(F("Cartao nao e MIFARE Classic (UID de 4 bytes esperado)."));
    return false;
void iniciarBipes(uint8_t n, unsigned int duracao, unsigned int pausa) {
  bipesRestantes = n;
  durBipe = duracao;
  pausaBipe = pausa;
  buzzerLigado = false;
  digitalWrite(BUZZER, LOW);
  tBipe = millis() - pausa;   // começa já
}

void atualizarBipes() {
  unsigned long agora = millis();
  if (buzzerLigado) {
    if (agora - tBipe >= durBipe) {
      digitalWrite(BUZZER, LOW);
      buzzerLigado = false;
      tBipe = agora;
    }
  } else if (bipesRestantes > 0 && agora - tBipe >= pausaBipe) {
    digitalWrite(BUZZER, HIGH);
    buzzerLigado = true;
    tBipe = agora;
    bipesRestantes--;
  }
}

  bool sucesso = nfc.mifareclassic_AuthenticateBlock(
    uid, uidLength, blocoTipo, 0, chaveA
  );
void bipeOk()      { iniciarBipes(1, 120, 100); }
void bipeErro()    { iniciarBipes(3, 120, 120); }
void bipeSemDestino() { iniciarBipes(3, 350, 150); }

  if (!sucesso) {
    Serial.println(F("Falha na autenticacao (chave diferente ou cartao nao e Classic)."));
// ---------------------- PN532 ----------------------
bool iniciarPN532() {
  nfc.begin();
  uint32_t versao = nfc.getFirmwareVersion();
  if (!versao) {
    depurar(F("PN532 nao encontrado (confira fios e chaves DIP)"));
    return false;
  }
  nfc.setPassiveActivationRetries(0x02);  // não fica esperando para sempre
  nfc.SAMConfig();
  depurar(F("PN532 ok"));
  return true;
}

void mostrarUID() {
  Serial.print(F("UID: "));
  for (uint8_t i = 0; i < uidLength; i++) {
    if (uid[i] < 0x10) Serial.print('0');
    Serial.print(uid[i], HEX);
    Serial.print(' ');
  }
  Serial.println();
void reiniciarPN532() {
  depurar(F("reiniciando PN532"));
  pn532Ok = iniciarPN532();
}

// ===== GRAVACAO =====
void gravarCartao() {
  titulo(F("NOVA GRAVACAO"));

  Serial.println(F("Digite o texto (maximo 16 caracteres):"));
// Lê o bloco 4 e devolve a doca (1..3), ou -1 se o adesivo não é válido
int8_t lerDoca(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  if (!nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave)) return -1;

  while (Serial.available()) Serial.read();
  while (Serial.available() == 0) { }
  uint8_t dados[16];
  if (!nfc.mifareclassic_ReadDataBlock(BLOCO, dados)) return -1;

  String entrada = Serial.readStringUntil('\n');
  entrada.trim();
  entrada.toUpperCase();
  if (memcmp(dados, "DOCA ", 5) != 0) return -1;
  uint8_t n = dados[5] - '0';
  if (n < 1 || n > 3) return -1;
  return (int8_t)n;
}

  if (entrada.length() == 0) {
    Serial.println(F("Texto vazio."));
void operar(uint8_t *uid, uint8_t uidLen) {
  int8_t doca = lerDoca(uid, uidLen);
  if (doca < 0) {
    depurar(F("adesivo invalido"));
    bipeErro();
    definirAtraso(ATRASO_ERRO_MS);
    return;
  }
  if (entrada.length() > 16) entrada = entrada.substring(0, 16);

  for (uint8_t i = 0; i < 16; i++) {
    dados[i] = (i < entrada.length()) ? entrada[i] : ' ';
  Serial.print(F("CAIXA:"));
  Serial.println(doca);
  bipeOk();
  definirAtraso(ATRASO_LEITURA_VALIDA_MS);
}

void gravar(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  uint8_t dados[16] = {0};
  memcpy(dados, "DOCA ", 5);
  dados[5] = '0' + DOCA_GRAVAR;

  bool ok = nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave)
            && nfc.mifareclassic_WriteDataBlock(BLOCO, dados);
  if (ok) {
    uint8_t conferencia[16];
    ok = nfc.mifareclassic_ReadDataBlock(BLOCO, conferencia)
         && memcmp(conferencia, dados, 16) == 0;
  }

  Serial.print(F("Texto: "));
  Serial.println(entrada);
  linha();

  esperarCartao();
  mostrarUID();
  linha();

  if (autenticarBloco() && nfc.mifareclassic_WriteDataBlock(blocoTipo, dados)) {
    Serial.println(F("Cartao cadastrado com sucesso!"));
    bipDuplo();
  if (ok) {
    depurar(F("adesivo gravado"));
    bipeOk();
    definirAtraso(ATRASO_LEITURA_VALIDA_MS);
  } else {
    Serial.println(F("Erro ao gravar o cartao."));
    bipErro();
    depurar(F("falha ao gravar"));
    bipeErro();
    definirAtraso(ATRASO_ERRO_MS);
  }
  linha();

  esperarRetirada();
  linha('=');
}

// ===== LEITURA =====
void lerCartao() {
  titulo(F("NOVA LEITURA"));

  esperarCartao();
  mostrarUID();
  linha();

  memset(dados, 0, sizeof(dados));

  if (autenticarBloco() && nfc.mifareclassic_ReadDataBlock(blocoTipo, dados)) {
    Serial.print(F("Texto lido: "));
    for (uint8_t i = 0; i < 16; i++) Serial.write(dados[i]);
    Serial.println();
    bipDuplo();
    enviarComandoMotor();   // avisa o Arduino do motor
  } else {
    Serial.println(F("Erro ao ler o cartao."));
    bipErro();
// ---------------------- serial vinda da esteira ----------------------
void lerSerialEsteira() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (posRx > 0) {
        linhaRx[posRx] = 0;
        if (strcmp(linhaRx, "ERRO") == 0) bipeSemDestino();
        posRx = 0;
      }
    } else if (posRx < sizeof(linhaRx) - 1) {
      linhaRx[posRx++] = c;
    } else {
      posRx = 0;  // linha longa demais: descarta
    }
  }
  linha();

  esperarRetirada();
  linha('=');
}

// ===== INICIALIZACAO =====
// ---------------------- setup / loop ----------------------
void setup() {
  Serial.begin(9600);
  Serial.setTimeout(30000);

  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);
  Serial.begin(9600);
  delay(2000);  // dá tempo da esteira iniciar

  titulo(F("INICIANDO PN532"));
  pn532Ok = iniciarPN532();
  if (FUNCAO == 1) Serial.println(F("RESET"));
  if (pn532Ok) bipeOk(); else bipeErro();
}

  // Reinicia o PN532 por codigo
  uint32_t versao = reiniciarPN532();
  if (!versao) {
    Serial.println(F("ERRO: PN532 nao encontrado."));
    Serial.println(F("Verifique a ligacao SPI e as chaves DIP (SEL0=OFF, SEL1=ON)."));
    linha('=');
    bipErro();
    while (true) delay(1000);
void loop() {
  atualizarBipes();
  lerSerialEsteira();

  unsigned long agora = millis();

  // PN532 fora: tenta de novo a cada 2 s
  if (!pn532Ok) {
    if (agora - tUltimaTentativa >= 2000) {
      tUltimaTentativa = agora;
      pn532Ok = iniciarPN532();
      if (!pn532Ok) bipeErro();
    }
    return;
  }

  Serial.print(F("Firmware PN5"));
  Serial.print((versao >> 24) & 0xFF, HEX);
  Serial.print(F(" v"));
  Serial.print((versao >> 16) & 0xFF);
  Serial.print('.');
  Serial.println((versao >> 8) & 0xFF);
  Serial.println(F("PN532 reiniciado com sucesso!"));

  // Reinicia o motor e o sensor (Arduino do motor)
  resetarArduinoMotor();
  Serial.println(F("Reset enviado ao motor e ao sensor."));

  Serial.println(funcao == 0 ? F("MODO: GRAVACAO") : F("MODO: LEITURA"));
  linha('=');
  bip(100);
}
  // atraso após leitura (sem travar o resto)
  if (agora - tAtraso < atrasoMs) return;

  uint8_t uid[7];
  uint8_t uidLen = 0;
  if (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLen, 100)) {
    // sem adesivo: aproveita para ver se o PN532 continua vivo
    if (agora - tVerifica >= VERIFICA_PN532_MS) {
      tVerifica = agora;
      if (nfc.getFirmwareVersion() == 0) reiniciarPN532();
    }
    return;
  }

void loop() {
  if (funcao == 0) gravarCartao();
  else lerCartao();
  if (FUNCAO == 0) gravar(uid, uidLen);
  else             operar(uid, uidLen);
}
