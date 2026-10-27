#include <SPI.h>
#include <Adafruit_PN532.h>

// ===== CONFIGURACOES =====
#define SS_PIN 10
#define BUZZER 8

// 0 = GRAVAR | 1 = LER
int funcao = 1;

// Bloco de dados do setor 1 (evita o setor 0 e os blocos de trailer 3, 7, 11...)
uint8_t blocoTipo = 4;

// Chave padrao A do MIFARE Classic
uint8_t chaveA[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

Adafruit_PN532 nfc(SS_PIN);

uint8_t uid[7];
uint8_t uidLength;
uint8_t dados[16];

// ===== RESET POR CODIGO =====
// Reinicia o PN532 por software. Retorna a versao do firmware (0 = falhou)
uint32_t reiniciarPN532() {
  nfc.begin();

  uint32_t versao = nfc.getFirmwareVersion();
  if (!versao) return 0;

  nfc.SAMConfig();
  nfc.setPassiveActivationRetries(0xFF);
  return versao;
}

// Manda o comando "RESET" pelo TX (pino 1) para o RX (pino 0) do Arduino do motor.
// Ele reinicia o motor e o sensor.
void resetarArduinoMotor() {
  Serial.println(F("RESET"));
  delay(100);
}

// Manda o comando "MOTOR" para o Arduino do motor comecar a girar
void enviarComandoMotor() {
  Serial.println(F("MOTOR"));
  Serial.println(F("Comando enviado ao motor."));
}

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

// ===== BUZZER =====
void bip(int duracao = 150) {
  digitalWrite(BUZZER, HIGH);
  delay(duracao);
  digitalWrite(BUZZER, LOW);
}

void bipDuplo() {
  bip(120);
  delay(100);
  bip(120);
}

// Som de erro: 3 bipes curtos e rapidos
void bipErro() {
  for (int i = 0; i < 3; i++) {
    bip(80);
    delay(80);
  }
}

// ===== FUNCOES AUXILIARES =====
void esperarCartao() {
  Serial.println(F("Aguardando cartao..."));

  while (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 500)) {
    // fica aqui em silencio
  }

  Serial.println(F("Cartao detectado!"));
  bip();
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
}

bool autenticarBloco() {
  if (uidLength != 4) {
    Serial.println(F("Cartao nao e MIFARE Classic (UID de 4 bytes esperado)."));
    return false;
  }

  bool sucesso = nfc.mifareclassic_AuthenticateBlock(
    uid, uidLength, blocoTipo, 0, chaveA
  );

  if (!sucesso) {
    Serial.println(F("Falha na autenticacao (chave diferente ou cartao nao e Classic)."));
    return false;
  }
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
}

// ===== GRAVACAO =====
void gravarCartao() {
  titulo(F("NOVA GRAVACAO"));

  Serial.println(F("Digite o texto (maximo 16 caracteres):"));

  while (Serial.available()) Serial.read();
  while (Serial.available() == 0) { }

  String entrada = Serial.readStringUntil('\n');
  entrada.trim();
  entrada.toUpperCase();

  if (entrada.length() == 0) {
    Serial.println(F("Texto vazio."));
    return;
  }
  if (entrada.length() > 16) entrada = entrada.substring(0, 16);

  for (uint8_t i = 0; i < 16; i++) {
    dados[i] = (i < entrada.length()) ? entrada[i] : ' ';
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
  } else {
    Serial.println(F("Erro ao gravar o cartao."));
    bipErro();
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
  }
  linha();

  esperarRetirada();
  linha('=');
}

// ===== INICIALIZACAO =====
void setup() {
  Serial.begin(9600);
  Serial.setTimeout(30000);

  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);

  titulo(F("INICIANDO PN532"));

  // Reinicia o PN532 por codigo
  uint32_t versao = reiniciarPN532();
  if (!versao) {
    Serial.println(F("ERRO: PN532 nao encontrado."));
    Serial.println(F("Verifique a ligacao SPI e as chaves DIP (SEL0=OFF, SEL1=ON)."));
    linha('=');
    bipErro();
    while (true) delay(1000);
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

void loop() {
  if (funcao == 0) gravarCartao();
  else lerCartao();
}
