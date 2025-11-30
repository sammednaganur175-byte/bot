/*
 * ESP8266 SERIAL LISTENER - USB Control
 * - Receives commands via USB Serial
 * - Controls L298N Motor Driver
 */

// Motor Speed (0 - 255) - PWM values
int CURRENT_FORWARD_SPEED = 120;
int CURRENT_TURN_SPEED = 120;

// ================= PIN DEFINITIONS =================
// L298N Motor Driver Pins
// Motor A (Left)
int ENA = D1; // PWM Speed Control
int IN1 = D3; // Direction 1
int IN2 = D4; // Direction 2

// Motor B (Right)
int ENB = D2; // PWM Speed Control
int IN3 = D5; // Direction 1
int IN4 = D8; // Direction 2

void setup() {
  Serial.begin(115200);
  Serial.println("ESP8266 Serial Motor Controller Ready");
  
  // Initialize Motor Pins
  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  
  Stop();
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    Serial.print("Received: ");
    Serial.println(command);
    
    if (command == "FORWARD") {
      Forward();
    }
    else if (command == "BACKWARD") {
      Backward();
    }
    else if (command == "LEFT") {
      TurnLeft();
    }
    else if (command == "RIGHT") {
      TurnRight();
    }
    else if (command == "STOP") {
      Stop();
    }
  }
}

void Forward() {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  analogWrite(ENA, CURRENT_FORWARD_SPEED);
  analogWrite(ENB, CURRENT_FORWARD_SPEED);
}

void Backward() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  analogWrite(ENA, CURRENT_FORWARD_SPEED);
  analogWrite(ENB, CURRENT_FORWARD_SPEED);
}

void TurnLeft() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  analogWrite(ENA, CURRENT_TURN_SPEED);
  analogWrite(ENB, CURRENT_TURN_SPEED);
}

void TurnRight() {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  analogWrite(ENA, CURRENT_TURN_SPEED);
  analogWrite(ENB, CURRENT_TURN_SPEED);
}

void Stop() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 0); analogWrite(ENB, 0);
}