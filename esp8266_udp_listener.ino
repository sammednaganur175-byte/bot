/*
 * HUMAN FOLLOWER ROBOT - ESP8266 RECEIVER CODE
 * - Listens for UDP commands from Python script
 * - Controls L298N Motor Driver (4-Pin Logic)
 * - Ultrasonic Safety Stop enabled
 * - UPDATED: Reduced speed to compensate for camera latency
 */

#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <NewPing.h>

// ================= CONFIGURATION =================
// !!! CHANGE THESE TO YOUR WIFI CREDENTIALS !!!
const char* ssid = "Poco M6 Pro 5g";
const char* password = "12345679";

// UDP Settings (Must match Python script)
unsigned int udpPort = 8888;
unsigned int statusPort = 8889;
IPAddress pythonIP;

// Motor Speed (0 - 255) - PWM values
// INCREASED SPEED to overcome motor static friction
int SPEED = 200;       // Default forward speed (increased)
int TURN_SPEED = 180;  // Default turn speed (increased for better turning)
int CURRENT_FORWARD_SPEED = 200;
int CURRENT_TURN_SPEED = 180;

// Individual motor speeds for differential control
int leftMotorSpeed = 150;
int rightMotorSpeed = 150;

// Ultrasonic Safety Settings
#define TRIG_PIN D6
#define ECHO_PIN D7
#define MAX_DISTANCE 200 // Maximum distance we want to ping for (in cm)
#define SAFE_DISTANCE 100 // Stop if obstacle is closer than this (in cm)

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

// ================= OBJECTS =================
WiFiUDP udp;
WiFiUDP statusUdp;
char packetBuffer[255]; // Buffer to hold incoming packet
NewPing sonar(TRIG_PIN, ECHO_PIN, MAX_DISTANCE);
unsigned long lastStatusSend = 0;

void setup() {
  // 1. Initialize Serial for debugging
  Serial.begin(115200);
  Serial.println("\n--- Robot Booting ---");

  // 2. Initialize Motor Pins
  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  
  // Start with motors stopped
  Stop();

  // 3. Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  Serial.print("Robot IP Address: ");
  Serial.println(WiFi.localIP()); // <--- USE THIS IP IN YOUR PYTHON SCRIPT

  // 4. Start UDP Listener
  udp.begin(udpPort);
  statusUdp.begin(statusPort);
  Serial.printf("Listening for UDP commands on port %d\n", udpPort);
  Serial.printf("Status updates on port %d\n", statusPort);
}

void loop() {
  // --- SAFETY CHECK FIRST ---
  // Check distance using Ultrasonic sensor
  int distance = sonar.ping_cm();
  
  // Send status update every 500ms
  if (millis() - lastStatusSend > 500) {
    if (pythonIP != IPAddress(0,0,0,0)) {
      String statusMsg = "DIST:" + String(distance);
      statusUdp.beginPacket(pythonIP, statusPort);
      statusUdp.write(statusMsg.c_str());
      statusUdp.endPacket();
    }
    lastStatusSend = millis();
  }
  
  // If distance is valid (>0) AND too close (<SAFE_DISTANCE)
  if (distance > 0 && distance < SAFE_DISTANCE) {
    // Force Stop
    Stop();
    return; // Skip the rest of the loop (ignore commands)
  }

  // --- READ UDP COMMANDS ---
  int packetSize = udp.parsePacket();
  if (packetSize) {
    // Read the packet into the buffer
    int len = udp.read(packetBuffer, 255);
    if (len > 0) {
      packetBuffer[len] = 0; // Null-terminate the string
    }
    
    String command = String(packetBuffer);
    Serial.print("CMD Received: ");
    Serial.println(command);
    
    // Store sender IP for status updates
    pythonIP = udp.remoteIP();

    // --- PARSE SPEED COMMANDS ---
    if (command.indexOf(':') > 0) {
      int colonIndex = command.indexOf(':');
      String cmdType = command.substring(0, colonIndex);
      int speed = command.substring(colonIndex + 1).toInt();
      
      if (cmdType == "SPEED") {
        // Overall speed control
        CURRENT_FORWARD_SPEED = constrain(speed, 50, 255);
        CURRENT_TURN_SPEED = constrain(speed, 30, 150);
      }
      else if (cmdType == "LEFT_SPEED") {
        leftMotorSpeed = constrain(speed, 50, 255);
      }
      else if (cmdType == "RIGHT_SPEED") {
        rightMotorSpeed = constrain(speed, 50, 255);
      }
      else if (cmdType == "FORWARD") {
        CURRENT_FORWARD_SPEED = constrain(speed, 100, 255);  // Minimum 100 for movement
        Forward();
      }
      else if (cmdType == "BACKWARD") {
        CURRENT_FORWARD_SPEED = constrain(speed, 100, 255);
        Backward();
      }
      else if (cmdType == "LEFT") {
        CURRENT_TURN_SPEED = constrain(speed, 120, 255);  // Increased minimum for better turning
        TurnLeft();
      }
      else if (cmdType == "RIGHT") {
        CURRENT_TURN_SPEED = constrain(speed, 120, 255);  // Increased minimum for better turning
        TurnRight();
      }
    }
    else {
      // --- EXECUTE MOTOR LOGIC (without speed) ---
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
      else if (command == "MOTOR_TEST") {
        MotorTest();
      }
      else if (command == "FORWARD_DIFF") {
        ForwardDifferential();
      }
    }
  }
}

// ================= MOTOR FUNCTIONS =================

void Forward() {
  // Motor A Forward
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  // Motor B Forward
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  // Set Speed
  analogWrite(ENA, CURRENT_FORWARD_SPEED);
  analogWrite(ENB, CURRENT_FORWARD_SPEED);
}

void TurnLeft() {
  // Rotate Left in place (Pivot Turn)
  // Motor A Backward
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  // Motor B Forward
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  // Set Speed
  analogWrite(ENA, CURRENT_TURN_SPEED);
  analogWrite(ENB, CURRENT_TURN_SPEED);
}

void TurnRight() {
  // Rotate Right in place (Pivot Turn)
  // Motor A Forward
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  // Motor B Backward
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  // Set Speed
  analogWrite(ENA, CURRENT_TURN_SPEED);
  analogWrite(ENB, CURRENT_TURN_SPEED);
}

void Stop() {
  // Stop logic signals
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  // Cut power
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
}

void Backward() {
  // Motor A Backward
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  // Motor B Backward
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  // Set Speed
  analogWrite(ENA, CURRENT_FORWARD_SPEED);
  analogWrite(ENB, CURRENT_FORWARD_SPEED);
}

void MotorTest() {
  Serial.println("Starting Motor Test...");
  
  // Test Motor A (Left) Forward
  Serial.println("Testing Left Motor Forward");
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 255); analogWrite(ENB, 0);
  delay(1000);
  Stop();
  delay(500);
  
  // Test Motor A (Left) Backward
  Serial.println("Testing Left Motor Backward");
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 255); analogWrite(ENB, 0);
  delay(1000);
  Stop();
  delay(500);
  
  // Test Motor B (Right) Forward
  Serial.println("Testing Right Motor Forward");
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  analogWrite(ENA, 0); analogWrite(ENB, 255);
  delay(1000);
  Stop();
  delay(500);
  
  // Test Motor B (Right) Backward
  Serial.println("Testing Right Motor Backward");
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  analogWrite(ENA, 0); analogWrite(ENB, 255);
  delay(1000);
  Stop();
  delay(500);
  
  // Test Both Motors Forward
  Serial.println("Testing Both Motors Forward");
  Forward();
  delay(2000);
  Stop();
  
  Serial.println("Motor Test Complete");
}

void ForwardDifferential() {
  // Motor A Forward
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  // Motor B Forward
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  // Set individual speeds
  analogWrite(ENA, leftMotorSpeed);
  analogWrite(ENB, rightMotorSpeed);
}