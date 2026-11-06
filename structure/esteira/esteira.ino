/*
  ESTEIRA - Arduino da esteira
  Motor de passo 28BYJ-48 (ULN2003), 3 sensores HC-SR04, 3 servos.

  Ligações:
    ULN2003:  IN1=8  IN2=9  IN3=10  IN4=11  (ordem normal)
    HC-SR04 1 (doca 1): TRIG=A0  ECHO=A1
    HC-SR04 2 (doca 2): TRIG=A2  ECHO=A3
    HC-SR04 3 (doca 3): TRIG=A4  ECHO=A5
    Servo 1=5   Servo 2=6   Servo 3=7
    LED externo (com resistor 220-330 ohm): pino 13
    Serial: RX (pino 0) <- TX (pino 1) do leitor
            TX (pino 1) -> RX (pino 0) do leitor
            GND comum entre as placas
    ATENÇÃO: motor e servos devem ter fonte externa de 5 V (GND em comum).

  A doca 1 é a mais perto do leitor, a doca 3 a mais longe.

  Protocolo serial (9600, linhas terminadas em \n):
    recebe:  RESET        limpa a fila e desliga a esteira
             CAIXA:n      nova caixa no fim da fila, destino = doca n (1..3)
    envia:   ERRO         caixa detectada sem destino (o buzzer do leitor apita)
             # texto      depuração (o leitor ignora)

  Lógica:
    - A fila guarda o destino de cada caixa, na ordem em que foram cadastradas.
    - Cada sensor lembra quantas caixas da fila já passaram por ele.
    - Quando um sensor vê uma caixa: se o destino dela é a doca do sensor, a
      esteira pausa, o servo bate e volta, e a esteira anda de novo.
      Se o destino é uma doca mais à frente, a caixa passa direto.
    - Fila vazia = motor desligado.

  IMPORTANTE: ao fazer upload, desconecte o fio do pino 0 (RX).
*/

#include <Servo.h>

// ===================== CONFIGURAÇÃO =====================
const bool DEBUG = false;   // true = imprime mensagens "# ..." na serial

const uint8_t MOTOR_PINOS[4] = {8, 9, 10, 11};
const uint8_t TRIG_PINOS[3]  = {A0, A2, A4};
const uint8_t ECHO_PINOS[3]  = {A1, A3, A5};
const uint8_t SERVO_PINOS[3] = {5, 6, 7};
const uint8_t LED_SENSOR = 13;

// Sensores
const uint8_t DIST_DETECTA_CM = 10;   // objeto a 10 cm ou menos = caixa presente
const uint8_t DIST_LIBERA_CM  = 14;   // acima disso = caixa saiu (histerese)
const uint8_t CONFIRMACOES    = 2;    // leituras seguidas para confirmar
const unsigned long INTERVALO_SENSOR_MS = 20;  // um sensor lido a cada 20 ms
const unsigned long ECHO_TIMEOUT_US = 2500;    // ~40 cm, evita travar o motor

// Servos (ajuste 0/90 se algum servo ficar do lado oposto, ex.: repouso 180 e bate 90)
const uint8_t ANG_REPOUSO[3] = {0, 0, 0};
const uint8_t ANG_BATE[3]    = {90, 90, 90};
const unsigned int TEMPO_ASSENTAR_MS = 150;  // espera a caixa parar antes de bater
const unsigned int TEMPO_BATIDA_MS   = 250;  // tempo com o servo estendido

// Motor de passo (passo completo, 2048 passos por volta)
const int PASSOS_VOLTA = 2048;
const uint8_t RPM_MIN = 6;
const uint8_t RPM_MAX = 17;
const unsigned int RAMPA_MS = 150;     // +1 RPM a cada 150 ms
const bool SENTIDO_NORMAL = true;      // false inverte o sentido da esteira

const uint8_t MAX_FILA = 20;
// ========================================================

const uint8_t SEQ[4][4] = {
  {1, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 1},
  {1, 0, 0, 1}
};

Servo servos[3];

// fila de caixas (guarda a doca de destino, 1..3)
uint8_t fila[MAX_FILA];
uint8_t qtd = 0;
// quantas caixas da fila já passaram por cada sensor
uint8_t passou[3] = {0, 0, 0};

// estado dos sensores
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

// serial
char linha[24];
uint8_t posLinha = 0;

// ---------------------- utilidades ----------------------
void depurar(const __FlashStringHelper* msg, int valor = -1) {
  if (!DEBUG) return;
  Serial.print(F("# "));
  Serial.print(msg);
  if (valor >= 0) {
    Serial.print(' ');
    Serial.print(valor);
  }
  Serial.println();
}

void enviarErro(const __FlashStringHelper* motivo) {
  Serial.println(F("ERRO"));
  depurar(motivo);
}

// ---------------------- motor ----------------------
void aplicarFase() {
  for (uint8_t i = 0; i < 4; i++) digitalWrite(MOTOR_PINOS[i], SEQ[faseMotor][i]);
}

void ligarMotor() {
  if (motorLigado) return;
  motorLigado = true;
  rpmAtual = RPM_MIN;            // sempre arranca devagar (rampa)
  tRampa = millis();
  tUltimoPassoUs = micros();
  depurar(F("motor ligado"));
}

// só para de dar passos, mantém as bobinas energizadas (segura a esteira)
void pausarMotor() {
  motorLigado = false;
}

// para e solta as bobinas (não esquenta)
void desligarMotor() {
  motorLigado = false;
  for (uint8_t i = 0; i < 4; i++) digitalWrite(MOTOR_PINOS[i], LOW);
  depurar(F("motor desligado"));
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
  depurar(F("reset"));
}

void adicionarCaixa(uint8_t doca) {
  if (qtd >= MAX_FILA) {
    enviarErro(F("fila cheia"));
    return;
  }
  fila[qtd++] = doca;
  depurar(F("caixa na fila, doca"), doca);
  ligarMotor();
}

// remove a caixa de índice idx, que estava no sensor "sensor" (0..2)
void removerCaixa(uint8_t idx, uint8_t sensor) {
  for (uint8_t k = idx; k + 1 < qtd; k++) fila[k] = fila[k + 1];
  qtd--;
  // os sensores antes deste já tinham contado essa caixa
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
  servos[s].write(ANG_REPOUSO[s]);   // volta e a esteira anda junto

  removerCaixa(idx, s);
  depurar(F("entregue na doca"), s + 1);

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
  if (duracao == 0) return 999;   // nada por perto
  return duracao / 58;
}

// um sensor viu uma caixa nova
void tratarDeteccao(uint8_t s) {
  uint8_t idx = passou[s];

  if (idx >= qtd) {
    enviarErro(F("caixa sem destino no sensor"));
    return;
  }

  uint8_t destino = fila[idx];
  uint8_t doca = s + 1;

  if (destino == doca) {
    entregar(s, idx);
  } else if (destino > doca) {
    passou[s]++;                       // passa direto
    depurar(F("passou direto no sensor"), doca);
  } else {
    // devia ter sido entregue antes: tira da fila para não travar a esteira
    removerCaixa(idx, s);
    enviarErro(F("caixa passou da sua doca"));
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
  // qualquer outra linha (ex.: "# ...") é ignorada
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
      posLinha = 0;  // linha longa demais: descarta
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

  depurar(F("esteira pronta"));
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
