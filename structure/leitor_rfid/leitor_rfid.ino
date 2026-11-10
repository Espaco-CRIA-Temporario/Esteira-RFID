// LEITOR RFID - PN532 (SPI), buzzer e LED
// PN532: SCK=13 MISO=12 MOSI=11 SS=10 | Buzzer=8 | LED=7
// Serial cruzada com a esteira + GND comum
// Upload: desconecte o fio do pino 0

#include <SPI.h>
#include <Adafruit_PN532.h>

const uint8_t FUNCAO      = 1;   // 0 = gravar adesivo, 1 = operar
const uint8_t DOCA_GRAVAR = 1;   // doca gravada no modo 0 (1, 2 ou 3)

#define SS_PIN 10
#define BUZZER 8
#define LED_LEITURA 7

const uint8_t BLOCO = 4;
const unsigned long ATRASO_VALIDO_MS = 3000;
const unsigned long ATRASO_ERRO_MS   = 1500;
const unsigned long LED_ACESO_MS     = 500;

Adafruit_PN532 nfc(SS_PIN);

bool pn532Ok = false;
unsigned long tTentativa = 0;
unsigned long tAtraso = 0, atrasoMs = 0;

// bipes
uint8_t bipesRestantes = 0;
bool buzzerLigado = false;
unsigned long tBipe = 0;
unsigned int durBipe = 100, pausaBipe = 100;

// LED
bool ledLigado = false;
unsigned long tLed = 0;

// serial da esteira
char linhaRx[16];
uint8_t posRx = 0;

void definirAtraso(unsigned long ms) {
  tAtraso = millis();
  atrasoMs = ms;
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

void bipeOk()         { iniciarBipes(1, 120, 100); }  // leitura/gravação ok
void bipeErro()       { iniciarBipes(3, 120, 120); }  // adesivo inválido ou erro
void bipeSemDestino() { iniciarBipes(3, 350, 150); }  // esteira viu caixa sem destino

bool iniciarPN532() {
  nfc.begin();
  if (!nfc.getFirmwareVersion()) return false;
  nfc.setPassiveActivationRetries(0x02);
  nfc.SAMConfig();
  return true;
}

// Lê o bloco 4 e devolve a doca (1..3), ou -1 se inválido
int8_t lerDoca(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  uint8_t dados[16];
  if (!nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave)) return -1;
  if (!nfc.mifareclassic_ReadDataBlock(BLOCO, dados)) return -1;
  if (memcmp(dados, "DOCA ", 5) != 0) return -1;
  uint8_t n = dados[5] - '0';
  return (n >= 1 && n <= 3) ? n : -1;
}

void operar(uint8_t *uid, uint8_t uidLen) {
  int8_t doca = lerDoca(uid, uidLen);
  if (doca < 0) {
    bipeErro();
    definirAtraso(ATRASO_ERRO_MS);
    return;
  }
  Serial.print(F("CAIXA:"));
  Serial.println(doca);
  bipeOk();
  definirAtraso(ATRASO_VALIDO_MS);
}

void gravar(uint8_t *uid, uint8_t uidLen) {
  uint8_t chave[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  uint8_t dados[16] = {0};
  uint8_t conf[16];
  memcpy(dados, "DOCA ", 5);
  dados[5] = '0' + DOCA_GRAVAR;

  bool ok = nfc.mifareclassic_AuthenticateBlock(uid, uidLen, BLOCO, 0, chave)
            && nfc.mifareclassic_WriteDataBlock(BLOCO, dados)
            && nfc.mifareclassic_ReadDataBlock(BLOCO, conf)
            && memcmp(conf, dados, 16) == 0;

  if (ok) { bipeOk();   definirAtraso(ATRASO_VALIDO_MS); }
  else    { bipeErro(); definirAtraso(ATRASO_ERRO_MS); }
}

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
      posRx = 0;
    }
  }
}

void setup() {
  pinMode(BUZZER, OUTPUT);
  pinMode(LED_LEITURA, OUTPUT);
  digitalWrite(BUZZER, LOW);
  digitalWrite(LED_LEITURA, LOW);
  Serial.begin(9600);
  delay(2000);   // espera a esteira iniciar

  pn532Ok = iniciarPN532();
  if (FUNCAO == 1) Serial.println(F("RESET"));
  if (pn532Ok) bipeOk(); else bipeErro();
}

void loop() {
  atualizarBipes();
  atualizarLed();
  lerSerialEsteira();

  unsigned long agora = millis();

  // PN532 fora: tenta de novo a cada 2 s
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

  acenderLed();   // chip detectado

  if (FUNCAO == 0) gravar(uid, uidLen);
  else             operar(uid, uidLen);
}
