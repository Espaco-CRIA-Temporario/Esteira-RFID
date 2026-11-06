/*
  LEITOR RFID - Arduino do leitor (PN532 em SPI + buzzer)

  Ligações:
    PN532: SCK=13  MISO=12  MOSI=11  SS=10  VCC=5V  GND=GND
           chaves DIP: SEL0 = OFF, SEL1 = ON (modo SPI)
    Buzzer ATIVO: pino 8 e GND
    Serial: TX (pino 1) -> RX (pino 0) da esteira
            RX (pino 0) <- TX (pino 1) da esteira
            GND comum entre as duas placas

  Biblioteca necessária: Adafruit PN532

  Modos (constante FUNCAO):
    0 = GRAVAR  -> grava "DOCA n" no bloco 4 do adesivo (n = DOCA_GRAVAR)
    1 = OPERAR  -> lê o adesivo e manda a caixa para a esteira

  Protocolo serial (9600, linhas terminadas em \n):
    envia:   RESET        ao ligar, para a esteira limpar a fila
             CAIXA:n      leitura válida, caixa com destino na doca n (1..3)
             # texto      depuração (a esteira ignora)
    recebe:  ERRO         a esteira viu uma caixa sem destino

  Bipes:
    1 bipe curto   leitura válida (ou gravação ok)
    3 bipes curtos adesivo inválido / erro de leitura ou gravação / PN532 fora
    3 bipes longos a esteira detectou caixa sem destino

  IMPORTANTE: ao fazer upload, desconecte o fio do pino 0 (RX).
*/

#include <SPI.h>
#include <Adafruit_PN532.h>

// ===================== CONFIGURAÇÃO =====================
const uint8_t FUNCAO      = 1;   // 0 = gravar adesivo, 1 = operar
const uint8_t DOCA_GRAVAR = 1;   // usado só no modo 0 (1, 2 ou 3)
const bool    DEBUG       = false;

#define SS_PIN 10
#define BUZZER 8

const uint8_t BLOCO = 4;   // bloco de dados do MIFARE Classic (setor 1)

const unsigned long ATRASO_LEITURA_VALIDA_MS = 3000;  // ignora novas leituras após uma válida
const unsigned long ATRASO_ERRO_MS           = 1500;  // evita apitar sem parar no mesmo adesivo
const unsigned long VERIFICA_PN532_MS        = 15000; // confere se o PN532 continua respondendo
// ========================================================

static_assert(DOCA_GRAVAR >= 1 && DOCA_GRAVAR <= 3, "DOCA_GRAVAR deve ser 1, 2 ou 3");

Adafruit_PN532 nfc(SS_PIN);

bool pn532Ok = false;
unsigned long tUltimaTentativa = 0;
unsigned long tVerifica = 0;

// atraso sem travar (usa millis)
unsigned long tAtraso = 0;
unsigned long atrasoMs = 0;

// bipes sem travar
uint8_t bipesRestantes = 0;
bool buzzerLigado = false;
unsigned long tBipe = 0;
unsigned int durBipe = 100, pausaBipe = 100;

// linha recebida da esteira
char linhaRx[16];
uint8_t posRx = 0;

// ---------------------- utilidades ----------------------
void depurar(const __FlashStringHelper* msg) {
  if (!DEBUG) return;
  Serial.print(F("# "));
  Serial.println(msg);
}

void definirAtraso(unsigned long ms) {
  tAtraso = millis();
  atrasoMs = ms;
}

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

void bipeOk()      { iniciarBipes(1, 120, 100); }
void bipeErro()    { iniciarBipes(3, 120, 120); }
void bipeSemDestino() { iniciarBipes(3, 350, 150); }

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

void reiniciarPN532() {
  depurar(F("reiniciando PN532"));
  pn532Ok = iniciarPN532();
}

// Lê o bloco 4 e devolve a doca (1..3), ou -1 se o adesivo não é válido
int8_t lerDoca(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  if (!nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave)) return -1;

  uint8_t dados[16];
  if (!nfc.mifareclassic_ReadDataBlock(BLOCO, dados)) return -1;

  if (memcmp(dados, "DOCA ", 5) != 0) return -1;
  uint8_t n = dados[5] - '0';
  if (n < 1 || n > 3) return -1;
  return (int8_t)n;
}

void operar(uint8_t *uid, uint8_t uidLen) {
  int8_t doca = lerDoca(uid, uidLen);
  if (doca < 0) {
    depurar(F("adesivo invalido"));
    bipeErro();
    definirAtraso(ATRASO_ERRO_MS);
    return;
  }
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

  if (ok) {
    depurar(F("adesivo gravado"));
    bipeOk();
    definirAtraso(ATRASO_LEITURA_VALIDA_MS);
  } else {
    depurar(F("falha ao gravar"));
    bipeErro();
    definirAtraso(ATRASO_ERRO_MS);
  }
}

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
}

// ---------------------- setup / loop ----------------------
void setup() {
  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);
  Serial.begin(9600);
  delay(2000);  // dá tempo da esteira iniciar

  pn532Ok = iniciarPN532();
  if (FUNCAO == 1) Serial.println(F("RESET"));
  if (pn532Ok) bipeOk(); else bipeErro();
}

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

  if (FUNCAO == 0) gravar(uid, uidLen);
  else             operar(uid, uidLen);
}
