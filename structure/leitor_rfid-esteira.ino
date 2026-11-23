
// ESTEIRA COM LEITOR RFID + RELE JQC3F-5VDC-C + SERVO MOTOR - 1 Arduino
// PN532 (SPI): SCK=13 MISO=12 MOSI=11 SS=10
// Rele: IN=3 | Buzzer=8 | LED=7 | LED vermelho=9
// Servo motor: SINAL=5
// FUNCAO = 0 -> cadastra cartões | FUNCAO = 1 -> opera a esteira
// Mensagens no Monitor Serial a 9600 baud

#include <SPI.h>
#include <Adafruit_PN532.h>
#include <Servo.h>

const uint8_t FUNCAO = 1;

#define SS_PIN 10
#define RELE 3
#define BUZZER 8
#define LED_LEITURA 7
#define LED_VERMELHO 9
#define SERVO_PIN 5

const bool RELE_ATIVO_BAIXO = false;

const unsigned long TEMPO_ESTEIRA_MS = 2600;
const unsigned long ATRASO_APOS_PARADA_MS = 1000;
const unsigned long ATRASO_VALIDO_MS = 1000;
const unsigned long ATRASO_ERRO_MS = 1500;
const unsigned long LED_ACESO_MS = 2600;
const unsigned long LED_VERMELHO_MS = 1000;
const unsigned long TEMPO_SERVO_MS = 500;

const uint8_t BLOCO = 4;
const char MARCA[] = "ESTEIRA";

Adafruit_PN532 nfc(SS_PIN);
Servo servo;

bool pn532Ok = false;
bool motorLigado = false;
bool buzzerLigado = false;
bool ledLigado = false;
bool ledVermelhoLigado = false;

unsigned long tTentativa = 0;
unsigned long tAtraso = 0;
unsigned long atrasoMs = 0;
unsigned long tMotor = 0;
unsigned long tServo = 0;
unsigned long tBipe = 0;
unsigned long tLed = 0;
unsigned long tLedVermelho = 0;

uint8_t bipesRestantes = 0;
unsigned int durBipe = 100;
unsigned int pausaBipe = 100;

enum EstadoServo {
  SERVO_PARADO,
  SERVO_ESPERANDO,
  SERVO_IDA,
  SERVO_VOLTA
};

EstadoServo estadoServo = SERVO_PARADO;

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

  if (buzzerLigado && agora - tBipe >= durBipe) {
    digitalWrite(BUZZER, LOW);
    buzzerLigado = false;
    tBipe = agora;
  } 
  else if (!buzzerLigado && bipesRestantes > 0 &&
           agora - tBipe >= pausaBipe) {
    digitalWrite(BUZZER, HIGH);
    buzzerLigado = true;
    tBipe = agora;
    bipesRestantes--;
  }
}

void bipeOk() {
  iniciarBipes(1, 120, 100);
}

void bipeErro() {
  iniciarBipes(3, 120, 120);
}

void bipeParou() {
  iniciarBipes(2, 400, 200);
}

void ligarMotor() {
  digitalWrite(RELE, RELE_ATIVO_BAIXO ? LOW : HIGH);
  motorLigado = true;
  tMotor = millis();
}

void pararMotor() {
  digitalWrite(RELE, RELE_ATIVO_BAIXO ? HIGH : LOW);
  motorLigado = false;
  estadoServo = SERVO_ESPERANDO;
  tServo = millis();
}

void atualizarMotor() {
  if (motorLigado && millis() - tMotor >= TEMPO_ESTEIRA_MS) {
    pararMotor();
    bipeParou();
    definirAtraso(ATRASO_APOS_PARADA_MS);
  }
}

void atualizarServo() {
  unsigned long agora = millis();

  switch (estadoServo) {
    case SERVO_ESPERANDO:
      if (agora - tServo >= ATRASO_APOS_PARADA_MS) {
        servo.write(180);
        estadoServo = SERVO_IDA;
        tServo = agora;
      }
      break;

    case SERVO_IDA:
      if (agora - tServo >= TEMPO_SERVO_MS) {
        servo.write(0);
        estadoServo = SERVO_VOLTA;
        tServo = agora;
      }
      break;

    case SERVO_VOLTA:
      if (agora - tServo >= TEMPO_SERVO_MS) {
        estadoServo = SERVO_PARADO;
      }
      break;

    case SERVO_PARADO:
      break;
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

void acenderLedVermelho() {
  digitalWrite(LED_VERMELHO, HIGH);
  ledVermelhoLigado = true;
  tLedVermelho = millis();
}

void atualizarLedVermelho() {
  if (ledVermelhoLigado &&
      millis() - tLedVermelho >= LED_VERMELHO_MS) {
    digitalWrite(LED_VERMELHO, LOW);
    ledVermelhoLigado = false;
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

  if (!nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave))
    return false;

  if (!nfc.mifareclassic_ReadDataBlock(BLOCO, dados))
    return false;

  return memcmp(dados, MARCA, sizeof(MARCA) - 1) == 0;
}

void operar(uint8_t *uid, uint8_t uidLen) {
  if (!cartaoAutorizado(uid, uidLen)) {
    Serial.println(F("Cartao nao identificado"));
    acenderLedVermelho();
    definirAtraso(ATRASO_ERRO_MS);
    return;
  }

  Serial.println(F("Cartao identificado"));
  acenderLed();
  bipeOk();
  ligarMotor();
}

void gravar(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  uint8_t dados[16] = {0};
  uint8_t conf[16];

  memcpy(dados, MARCA, sizeof(MARCA) - 1);

  bool ok =
    nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave) &&
    nfc.mifareclassic_WriteDataBlock(BLOCO, dados) &&
    nfc.mifareclassic_ReadDataBlock(BLOCO, conf) &&
    memcmp(conf, dados, 16) == 0;

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
  pinMode(LED_VERMELHO, OUTPUT);

  digitalWrite(BUZZER, LOW);
  digitalWrite(LED_LEITURA, LOW);
  digitalWrite(LED_VERMELHO, LOW);

  servo.attach(SERVO_PIN);
  servo.write(0);

  pn532Ok = iniciarPN532();

  if (pn532Ok) bipeOk();
  else bipeErro();
}

void loop() {
  atualizarBipes();
  atualizarLed();
  atualizarLedVermelho();
  atualizarMotor();
  atualizarServo();

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
  if (estadoServo != SERVO_PARADO) return;

  uint8_t uid[7];
  uint8_t uidLen = 0;

  if (!nfc.readPassiveTargetID(
        PN532_MIFARE_ISO14443A, uid, &uidLen, 100))
    return;

  if (FUNCAO == 0) {
    acenderLed();
    gravar(uid, uidLen);
  } else {
    operar(uid, uidLen);
  }
}
