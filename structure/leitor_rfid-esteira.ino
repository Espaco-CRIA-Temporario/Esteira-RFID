// ESTEIRA COM LEITOR RFID + RELE JQC3F-5VDC-C - 1 Arduino
// PN532 (SPI): SCK=13 MISO=12 MOSI=11 SS=10
// Rele: IN=3 | Buzzer=8 | LED=7
// FUNCAO = 0 -> cadastra cartões | FUNCAO = 1 -> opera a esteira
// Mensagens no Monitor Serial a 9600 baud

#include <SPI.h>
#include <Adafruit_PN532.h>

const uint8_t FUNCAO = 1;

#define SS_PIN      10
#define RELE        3
#define BUZZER      8
#define LED_LEITURA 7

const bool RELE_ATIVO_BAIXO = true;

const unsigned long TEMPO_ESTEIRA_MS      = 4000;
const unsigned long ATRASO_APOS_PARADA_MS = 1000;
const unsigned long ATRASO_VALIDO_MS      = 1000;
const unsigned long ATRASO_ERRO_MS        = 1500;
const unsigned long LED_ACESO_MS          = 500;

const uint8_t BLOCO = 4;
const char MARCA[] = "ESTEIRA";

Adafruit_PN532 nfc(SS_PIN);

bool pn532Ok = false;
unsigned long tTentativa = 0;
unsigned long tAtraso = 0, atrasoMs = 0;

bool motorLigado = false;
unsigned long tMotor = 0;

uint8_t bipesRestantes = 0;
bool buzzerLigado = false;
unsigned long tBipe = 0;
unsigned int durBipe = 100, pausaBipe = 100;

bool ledLigado = false;
unsigned long tLed = 0;

void definirAtraso(unsigned long ms) {
  tAtraso = millis();
  atrasoMs = ms;
}

void iniciarBipes(uint8_t n, unsigned int dur, unsigned int pausa) {
  bipesRestantes = n;
  durBipe = dur;
  pausaBipe = pausa;
  buzzerLigado = false;
  digitalWrite(BUZZER, LOW);
  tBipe = millis() - pausa;
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

void bipeOk()    { iniciarBipes(1, 120, 100); }
void bipeErro()  { iniciarBipes(3, 120, 120); }
void bipeParou() { iniciarBipes(2, 400, 200); }

void ligarMotor() {
  digitalWrite(RELE, RELE_ATIVO_BAIXO ? LOW : HIGH);
  motorLigado = true;
  tMotor = millis();
}

void pararMotor() {
  digitalWrite(RELE, RELE_ATIVO_BAIXO ? HIGH : LOW);
  motorLigado = false;
}

void atualizarMotor() {
  if (motorLigado && millis() - tMotor >= TEMPO_ESTEIRA_MS) {
    pararMotor();
    bipeParou();
    definirAtraso(ATRASO_APOS_PARADA_MS);
  }
}

void acenderLed() {
  digitalWrite(LED_LEITURA, HIGH);
  ledLigado = true;
  tLed = millis();
}

void atualizarLed() {
  if (ledLigado && millis() - tLed >= LED_ACESO_MS) {
    digitalWrite(LED_LEITURA, LOW);
    ledLigado = false;
  }
}

bool iniciarPN532() {
  nfc.begin();
  if (!nfc.getFirmwareVersion()) {
    Serial.println(F("RFID nao encontrado"));
    return false;
  }
  nfc.setPassiveActivationRetries(0x02);
  nfc.SAMConfig();
  Serial.println(F("RFID iniciado"));
  return true;
}

bool cartaoAutorizado(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  uint8_t dados[16];
  if (!nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave)) return false;
  if (!nfc.mifareclassic_ReadDataBlock(BLOCO, dados)) return false;
  return memcmp(dados, MARCA, sizeof(MARCA) - 1) == 0;
}

void operar(uint8_t *uid, uint8_t uidLen) {
  if (!cartaoAutorizado(uid, uidLen)) {
    Serial.println(F("Cartao nao identificado"));
    bipeErro();
    definirAtraso(ATRASO_ERRO_MS);
    return;
  }
  Serial.println(F("Cartao identificado"));
  bipeOk();
  ligarMotor();
}

void gravar(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  uint8_t dados[16] = {0};
  uint8_t conf[16];
  memcpy(dados, MARCA, sizeof(MARCA) - 1);

  bool ok = nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave)
            && nfc.mifareclassic_WriteDataBlock(BLOCO, dados)
            && nfc.mifareclassic_ReadDataBlock(BLOCO, conf)
            && memcmp(conf, dados, 16) == 0;

  if (ok) {
    Serial.println(F("Cartao cadastrado"));
    bipeOk();
    definirAtraso(ATRASO_VALIDO_MS);
  } else {
    Serial.println(F("Falha ao cadastrar o cartao"));
    bipeErro();
    definirAtraso(ATRASO_ERRO_MS);
  }
}

void setup() {
  Serial.begin(9600);

  digitalWrite(RELE, RELE_ATIVO_BAIXO ? HIGH : LOW);
  pinMode(RELE, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  pinMode(LED_LEITURA, OUTPUT);

  digitalWrite(BUZZER, LOW);
  digitalWrite(LED_LEITURA, LOW);

  pn532Ok = iniciarPN532();
  if (pn532Ok) bipeOk(); else bipeErro();
}

void loop() {
  atualizarBipes();
  atualizarLed();
  atualizarMotor();

  if (motorLigado) return;

  unsigned long agora = millis();

  if (!pn532Ok) {
    if (agora - tTentativa >= 2000) {
      tTentativa = agora;
      pn532Ok = iniciarPN532();
      if (!pn532Ok) bipeErro();
    }
    return;
  }

  if (agora - tAtraso < atrasoMs) return;

  uint8_t uid[7];
  uint8_t uidLen = 0;
  if (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLen, 100)) return;

  acenderLed();

  if (FUNCAO == 0) gravar(uid, uidLen);
  else             operar(uid, uidLen);
}
