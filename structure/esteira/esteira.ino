// ESTEIRA - motor de passo, 3 sensores HC-SR04, 3 servos
// ULN2003: 8,9,10,11 | Sensores TRIG/ECHO: A0/A1, A2/A3, A4/A5
// Servos: 5,6,7 | LED: 13
// Serial cruzada com o leitor + GND comum
// Upload: desconecte o fio do pino 0

#include <Servo.h>

const uint8_t MOTOR_PINOS[4] = {8, 9, 10, 11};
const uint8_t TRIG_PINOS[3]  = {A0, A2, A4};
const uint8_t ECHO_PINOS[3]  = {A1, A3, A5};
const uint8_t SERVO_PINOS[3] = {5, 6, 7};
const uint8_t LED_SENSOR = 13;

// Sensores
const uint8_t DIST_DETECTA_CM = 10;   // caixa presente
const uint8_t DIST_LIBERA_CM  = 14;   // caixa saiu
const uint8_t CONFIRMACOES    = 2;
const unsigned long INTERVALO_SENSOR_MS = 20;
const unsigned long ECHO_TIMEOUT_US = 2500;
const unsigned long INTERVALO_ERRO_MS = 1000;   // mínimo entre dois ERRO

// Servos
const uint8_t ANG_REPOUSO[3] = {0, 0, 0};
const uint8_t ANG_BATE[3]    = {90, 90, 90};
const unsigned int TEMPO_ASSENTAR_MS = 150;
const unsigned int TEMPO_BATIDA_MS   = 250;

// Motor (2048 passos por volta)
const int PASSOS_VOLTA = 2048;
const uint8_t RPM_MIN = 6;
const uint8_t RPM_MAX = 17;
const unsigned int RAMPA_MS = 150;
const bool SENTIDO_NORMAL = true;   // false inverte a esteira

const uint8_t MAX_FILA = 20;

const uint8_t SEQ[4][4] = {
  {1, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 1},
  {1, 0, 0, 1}
};

Servo servos[3];

// fila de destinos (docas 1..3)
uint8_t fila[MAX_FILA];
uint8_t qtd = 0;
uint8_t passou[3] = {0, 0, 0};   // caixas da fila que já passaram por cada sensor

// sensores
bool presente[3] = {false, false, false};
uint8_t contaOn[3]  = {0, 0, 0};
uint8_t contaOff[3] = {0, 0, 0};
uint8_t sensorAtual = 0;
unsigned long tSensor = 0;

// motor
bool motorLigado = false;
uint8_t faseMotor = 0;
uint8_t rpmAtual = RPM_MIN;
unsigned long tUltimoPassoUs = 0;
unsigned long tRampa = 0;

// erro
unsigned long tUltimoErro = 0;
bool jaTeveErro = false;

// serial
char linha[24];
uint8_t posLinha = 0;

// ---------------------- erro ----------------------
// s = sensor (1..3) que gerou o erro, ou 0 se não veio de sensor
void enviarErro(uint8_t s) {
  unsigned long agora = millis();
  if (jaTeveErro && agora - tUltimoErro < INTERVALO_ERRO_MS) return;
  jaTeveErro = true;
  tUltimoErro = agora;

  if (s > 0) {
    Serial.print(F("# sensor "));
    Serial.println(s);
  }
  Serial.println(F("ERRO"));
}

// ---------------------- motor ----------------------
void aplicarFase() {
  for (uint8_t i = 0; i < 4; i++) digitalWrite(MOTOR_PINOS[i], SEQ[faseMotor][i]);
}

void ligarMotor() {
  if (motorLigado) return;
  motorLigado = true;
  rpmAtual = RPM_MIN;
  tRampa = millis();
  tUltimoPassoUs = micros();
}

// para os passos mas mantém as bobinas energizadas
void pausarMotor() {
  motorLigado = false;
}

// para e solta as bobinas
void desligarMotor() {
  motorLigado = false;
  for (uint8_t i = 0; i < 4; i++) digitalWrite(MOTOR_PINOS[i], LOW);
}

void atualizarMotor() {
  if (!motorLigado) return;

  unsigned long agoraMs = millis();
  if (rpmAtual < RPM_MAX && agoraMs - tRampa >= RAMPA_MS) {
    rpmAtual++;
    tRampa = agoraMs;
  }

  unsigned long intervaloUs = 60000000UL / ((unsigned long)PASSOS_VOLTA * rpmAtual);
  unsigned long agoraUs = micros();
  if (agoraUs - tUltimoPassoUs >= intervaloUs) {
    tUltimoPassoUs = agoraUs;
    faseMotor = SENTIDO_NORMAL ? ((faseMotor + 1) & 3) : ((faseMotor + 3) & 3);
    aplicarFase();
  }
}

// ---------------------- fila ----------------------
void resetar() {
  qtd = 0;
  for (uint8_t s = 0; s < 3; s++) passou[s] = 0;
  desligarMotor();
}

void adicionarCaixa(uint8_t doca) {
  if (qtd >= MAX_FILA) {
    enviarErro(0);
    return;
  }
  fila[qtd++] = doca;
  ligarMotor();
}

// remove a caixa idx, que estava no sensor "sensor" (0..2)
void removerCaixa(uint8_t idx, uint8_t sensor) {
  for (uint8_t k = idx; k + 1 < qtd; k++) fila[k] = fila[k + 1];
  qtd--;
  for (uint8_t j = 0; j < sensor; j++) {
    if (passou[j] > 0) passou[j]--;
  }
}

// ---------------------- servos ----------------------
void entregar(uint8_t s, uint8_t idx) {
  pausarMotor();
  delay(TEMPO_ASSENTAR_MS);
  servos[s].write(ANG_BATE[s]);
  delay(TEMPO_BATIDA_MS);
  servos[s].write(ANG_REPOUSO[s]);

  removerCaixa(idx, s);

  if (qtd > 0) ligarMotor();
  else desligarMotor();
}

// ---------------------- sensores ----------------------
uint16_t lerDistanciaCm(uint8_t s) {
  digitalWrite(TRIG_PINOS[s], LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PINOS[s], HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PINOS[s], LOW);
  unsigned long duracao = pulseIn(ECHO_PINOS[s], HIGH, ECHO_TIMEOUT_US);
  if (duracao == 0) return 999;
  return duracao / 58;
}

// o sensor s viu uma caixa nova
void tratarDeteccao(uint8_t s) {
  uint8_t idx = passou[s];

  if (idx >= qtd) {           // caixa sem destino
    enviarErro(s + 1);
    return;
  }

  uint8_t destino = fila[idx];
  uint8_t doca = s + 1;

  if (destino == doca) {
    entregar(s, idx);
  } else if (destino > doca) {
    passou[s]++;              // passa direto
  } else {                    // passou da sua doca
    removerCaixa(idx, s);
    enviarErro(s + 1);
    if (qtd == 0) desligarMotor();
  }
}

void atualizarSensor(uint8_t s) {
  uint16_t cm = lerDistanciaCm(s);

  if (!presente[s]) {
    if (cm <= DIST_DETECTA_CM) {
      if (++contaOn[s] >= CONFIRMACOES) {
        contaOn[s] = 0;
        presente[s] = true;
        tratarDeteccao(s);
      }
    } else {
      contaOn[s] = 0;
    }
  } else {
    if (cm > DIST_LIBERA_CM) {
      if (++contaOff[s] >= CONFIRMACOES) {
        contaOff[s] = 0;
        presente[s] = false;
      }
    } else {
      contaOff[s] = 0;
    }
  }
}

// ---------------------- serial ----------------------
void processarLinha() {
  if (strcmp(linha, "RESET") == 0) {
    resetar();
  } else if (strncmp(linha, "CAIXA:", 6) == 0) {
    uint8_t doca = linha[6] - '0';
    if (doca >= 1 && doca <= 3) adicionarCaixa(doca);
  }
}

void lerSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (posLinha > 0) {
        linha[posLinha] = 0;
        processarLinha();
        posLinha = 0;
      }
    } else if (posLinha < sizeof(linha) - 1) {
      linha[posLinha++] = c;
    } else {
      posLinha = 0;
    }
  }
}

// ---------------------- setup / loop ----------------------
void setup() {
  Serial.begin(9600);

  for (uint8_t i = 0; i < 4; i++) {
    pinMode(MOTOR_PINOS[i], OUTPUT);
    digitalWrite(MOTOR_PINOS[i], LOW);
  }
  for (uint8_t s = 0; s < 3; s++) {
    pinMode(TRIG_PINOS[s], OUTPUT);
    digitalWrite(TRIG_PINOS[s], LOW);
    pinMode(ECHO_PINOS[s], INPUT);
    servos[s].attach(SERVO_PINOS[s]);
    servos[s].write(ANG_REPOUSO[s]);
  }
  pinMode(LED_SENSOR, OUTPUT);
  digitalWrite(LED_SENSOR, LOW);
}

void loop() {
  lerSerial();
  atualizarMotor();

  unsigned long agora = millis();
  if (agora - tSensor >= INTERVALO_SENSOR_MS) {
    tSensor = agora;
    atualizarSensor(sensorAtual);
    sensorAtual = (sensorAtual + 1) % 3;
    digitalWrite(LED_SENSOR, (presente[0] || presente[1] || presente[2]) ? HIGH : LOW);
  }
}
