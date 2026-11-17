// ESTEIRA - motor DC amarelo (TT), 3 sensores HC-SR04, 3 servos
// Driver ponte H (L298N / L9110 / TB6612): IN1=8, IN2=9, ENA (PWM)=11
// Sensores TRIG/ECHO: A0/A1, A2/A3, A4/A5
// Servos: 5,6,7 | LED: 13
// Serial cruzada com o leitor + GND comum
// Upload: desconecte o fio do pino 0
//
// OBS: o pino do PWM do motor precisa ser 3 ou 11 (o Servo.h desativa o PWM dos pinos 9 e 10).

#include <Servo.h>

const uint8_t MOTOR_IN1 = 8;
const uint8_t MOTOR_IN2 = 9;
const uint8_t MOTOR_PWM = 11;

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

// Servos
const uint8_t ANG_REPOUSO[3] = {0, 0, 0};
const uint8_t ANG_BATE[3]    = {90, 90, 90};
const unsigned int TEMPO_ASSENTAR_MS   = 80;    // espera a caixa parar antes de bater
const unsigned int TEMPO_CHEGAR_90_MS  = 300;   // espera o servo chegar em 90° antes de voltar a 0°

// Motor DC (PWM 0..255) - ajuste PWM_MIN/PWM_MAX para a velocidade da esteira
const uint8_t PWM_MIN = 110;        // abaixo disso o motor amarelo costuma não girar
const uint8_t PWM_MAX = 180;
const uint8_t PWM_PASSO = 5;
const unsigned int RAMPA_MS = 30;
const bool SENTIDO_NORMAL = true;   // false inverte a esteira

const uint8_t MAX_FILA = 20;

Servo servos[3];

// fila de destinos (docas 1..3)
uint8_t fila[MAX_FILA];
uint8_t qtd = 0;
uint8_t passou[3] = {0, 0, 0};   // caixas da fila que já passaram por cada sensor

// sensores
bool presente[3] = {false, false, false};
bool perto[3]    = {false, false, false};   // leitura direta (para o LED)
uint8_t contaOn[3]  = {0, 0, 0};
uint8_t contaOff[3] = {0, 0, 0};
uint8_t sensorAtual = 0;
unsigned long tSensor = 0;

// motor
bool motorLigado = false;
uint8_t pwmAtual = PWM_MIN;
unsigned long tRampa = 0;

// serial
char linha[24];
uint8_t posLinha = 0;

// ---------------------- motor ----------------------
void aplicarDirecao() {
  digitalWrite(MOTOR_IN1, SENTIDO_NORMAL ? HIGH : LOW);
  digitalWrite(MOTOR_IN2, SENTIDO_NORMAL ? LOW : HIGH);
}

void ligarMotor() {
  if (motorLigado) return;
  motorLigado = true;
  pwmAtual = PWM_MIN;
  tRampa = millis();
  aplicarDirecao();
  analogWrite(MOTOR_PWM, pwmAtual);
}

// freia o motor (para a esteira na hora, para o servo bater na caixa parada)
void pausarMotor() {
  motorLigado = false;
  digitalWrite(MOTOR_IN1, HIGH);
  digitalWrite(MOTOR_IN2, HIGH);
  analogWrite(MOTOR_PWM, 255);
}

// para e solta o motor
void desligarMotor() {
  motorLigado = false;
  analogWrite(MOTOR_PWM, 0);
  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, LOW);
}

void atualizarMotor() {
  if (!motorLigado) return;

  unsigned long agoraMs = millis();
  if (pwmAtual < PWM_MAX && agoraMs - tRampa >= RAMPA_MS) {
    pwmAtual = (PWM_MAX - pwmAtual > PWM_PASSO) ? pwmAtual + PWM_PASSO : PWM_MAX;
    analogWrite(MOTOR_PWM, pwmAtual);
    tRampa = agoraMs;
  }
}

// ---------------------- fila ----------------------
void resetar() {
  qtd = 0;
  for (uint8_t s = 0; s < 3; s++) passou[s] = 0;
  desligarMotor();
}

void adicionarCaixa(uint8_t doca) {
  if (qtd >= MAX_FILA) return;   // fila cheia: ignora
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

  servos[s].write(ANG_BATE[s]);        // vai a 90° na velocidade máxima
  delay(TEMPO_CHEGAR_90_MS);           // espera chegar em 90°
  servos[s].write(ANG_REPOUSO[s]);
