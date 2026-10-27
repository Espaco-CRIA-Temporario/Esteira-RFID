// Leitor RFID (PN532) -> envia o UID da tag pela Serial para o PC (script ponte.py).
//
// Formato enviado:   UID;04A1B2C3        (uma linha por leitura)
// Mensagens de status comecam com INFO;  (a ponte so mostra na tela)
// O PC responde:     OK   -> bipe duplo  | ERRO -> 3 bipes curtos
//
// Ligacao igual ao cadastro_item.ino: PN532 em modo SPI (SEL0=OFF, SEL1=ON), SS no pino 10,
// SCK=13, MISO=12, MOSI=11, buzzer no pino 8.

#include <SPI.h>
#include <Adafruit_PN532.h>

#define SS_PIN 10
#define BUZZER 8

Adafruit_PN532 nfc(SS_PIN);

uint8_t uid[7];
uint8_t uidLength;

// ===== BUZZER =====
void bip(int duracao = 150) {
  digitalWrite(BUZZER, HIGH);
  delay(duracao);
  digitalWrite(BUZZER, LOW);
}

void bipOk() {
  bip(120);
  delay(100);
  bip(120);
}

void bipErro() {
  for (int i = 0; i < 3; i++) {
    bip(80);
    delay(80);
  }
}

// ===== RESPOSTA DO PC =====
char buffer[16];
uint8_t tamanho = 0;

void lerRespostaDoPC() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      buffer[tamanho] = '\0';
      if (strcmp(buffer, "OK") == 0) bipOk();
      else if (strcmp(buffer, "ERRO") == 0) bipErro();
      tamanho = 0;
    } else if (c != '\r') {
      if (tamanho < sizeof(buffer) - 1) buffer[tamanho++] = c;
      else tamanho = 0;
    }
  }
}

// ===== ENVIO DO UID =====
void enviarUID() {
  Serial.print(F("UID;"));
  for (uint8_t i = 0; i < uidLength; i++) {
    if (uid[i] < 0x10) Serial.print('0');
    Serial.print(uid[i], HEX);
  }
  Serial.println();
}

// Espera o cartao sair do leitor (para nao ler a mesma tag varias vezes)
void esperarRetirada() {
  uint8_t uidTmp[7];
  uint8_t lenTmp;
  while (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uidTmp, &lenTmp, 300)) {
    lerRespostaDoPC();
    delay(100);
  }
  delay(300);
}

void setup() {
  Serial.begin(9600);

  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);

  nfc.begin();

  uint32_t versao = nfc.getFirmwareVersion();
  if (!versao) {
    Serial.println(F("INFO;ERRO: PN532 nao encontrado. Verifique o SPI e as chaves DIP."));
    while (true) {
      bipErro();
      delay(1000);
    }
  }

  nfc.SAMConfig();
  nfc.setPassiveActivationRetries(0xFF);

  Serial.println(F("INFO;PN532 pronto"));
  bip(100);
}

void loop() {
  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 500)) {
    bip(60);          // confirma que a tag foi lida
    enviarUID();

    // da ate 1,5 s para o PC responder e toca o bipe de OK/ERRO
    unsigned long inicio = millis();
    while (millis() - inicio < 1500) lerRespostaDoPC();

    esperarRetirada();
  }
}
