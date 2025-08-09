/*
  Smart Lunchbox - ESP32 (Wokwi)
  Publishes telemetry/events to test.mosquitto.org (MQTT TCP port 1883)
  HiveMQ (web) client can connect to same broker via WebSockets (port 8081)
  
  Hardware:
  - ESP32 DevKit
  - MPU6050 Accelerometer
  - DS18B20 Temperature Sensor
  - DHT22 Temperature/Humidity Sensor
  - MQ-135 Gas Sensor
  - Push Button (Box Open/Close)
  - RGB LED (Status)
  - Buzzer (Alerts)
  - Potentiometer (Weight Simulation)
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "DHT.h"
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include "azure_iot.h"

// ===== CONFIG =====
const char* ssid = "Wokwi-GUEST";   // Wokwi network
const char* password = "";          // Wokwi guest has no password

// MQTT settings for local testing (fallback)
const char* mqtt_server = "test.mosquitto.org";
const uint16_t mqtt_port = 1883;
const char* device_id = "lunchbox_esp32_sim";

// Telemetry topics
String topic_telemetry = String("lunchbox/") + device_id + "/telemetry";
String topic_events = String("lunchbox/") + device_id + "/events";

// Azure IoT Hub settings (override in azure_iot.h)
bool useAzureIoT = true;  // Set to false to use local MQTT broker

// ===== PINS =====
#define POT_PIN 35      // Potentiometer for weight simulation
#define ONEWIRE_PIN 25  // DS18B20 temperature sensor
#define DHTPIN 26       // DHT22 temperature/humidity sensor
#define MQ2_PIN 34      // MQ-135 gas sensor
#define BOX_PIN 27      // Push button for box open/close
#define LED_R 14        // RGB LED Red
#define LED_G 12        // RGB LED Green
#define LED_B 13        // RGB LED Blue
#define BUZZER 15       // Buzzer for alerts
#define SDA_PIN 21      // I2C SDA for MPU6050
#define SCL_PIN 22      // I2C SCL for MPU6050
#define CAMERA_BTN 4    // Button to simulate camera capture

// ===== SENSORS =====
OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);
DHT dht(DHTPIN, DHT22);
Adafruit_MPU6050 mpu;

// ===== MQTT / WiFi =====
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Azure IoT Hub client
#ifdef IOTHUB_HOSTNAME
#undef IOTHUB_HOSTNAME
#endif
#define IOTHUB_HOSTNAME "your-iot-hub.azure-devices.net"  // Replace with your IoT Hub hostname

// ===== State & thresholds =====
float lastWeight = 0.0;
unsigned long lastWeightTime = 0;
const float weightThresholdConsume = 5.0;   // grams
const float weightThresholdSharePct = 35.0; // percent
const unsigned long shareWindowMs = 8000;   // ms
const float unsafeTempC = 60.0;             // temperature threshold (°C)
const int unsafeGasLevel = 3000;            // ADC threshold for gas sensor
const int loopIntervalMs = 2000;            // telemetry interval
const float movementThreshold = 2.0;         // m/s² for movement detection
const int faceRecognitionTimeout = 5000;     // ms between face recognition attempts

unsigned long lastLoop = 0;
unsigned long lastHeartbeat = 0;

// ===== Helpers =====
void setRGB(bool r, bool g, bool b) {
  // common-cathode: LOW = ON in many Wokwi parts; adjust if needed
  digitalWrite(LED_R, r ? LOW : HIGH);
  digitalWrite(LED_G, g ? LOW : HIGH);
  digitalWrite(LED_B, b ? LOW : HIGH);
}

void beep(int ms) {
  digitalWrite(BUZZER, HIGH);
  delay(ms);
  digitalWrite(BUZZER, LOW);
}

void mqttPublish(const char* topic, const String &payload) {
  if (useAzureIoT) {
    // Use Azure IoT Hub
    if (isAzureConnected()) {
      azurePublish(AZURE_IOT_HUB_TOPIC, payload.c_str());
    } else {
      Serial.println("Azure IoT Hub not connected, attempting to reconnect...");
      azureConnect();
    }
  } else {
    // Fallback to local MQTT
    if (mqttClient.connected()) {
      mqttClient.publish(topic, payload.c_str());
    } else {
      Serial.println("MQTT not connected, cannot publish.");
      // Attempt to reconnect
      if (WiFi.status() == WL_CONNECTED) {
        mqttClient.connect(device_id);
      }
    }
  }
}

// ===== MQTT reconnect =====
void reconnect() {
  if (useAzureIoT) {
    if (!isAzureConnected()) {
      Serial.println("Attempting to connect to Azure IoT Hub...");
      if (!azureConnect()) {
        Serial.println("Failed to connect to Azure IoT Hub, will retry...");
      }
    }
  } else {
    if (mqttClient.connected()) return;
    Serial.print("Connecting to MQTT...");
    String clientId = String(device_id) + "-" + String(random(0xffff), HEX);
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("connected to MQTT broker");
    } else {
      Serial.print("failed rc=");
      Serial.print(mqttClient.state());
      Serial.println(", will retry...");
    }
  }
}

// ===== read pseudo-weight from potentiometer =====
float readWeight() {
  int potVal = analogRead(POT_PIN); // 0-4095
  // Map to grams (0 - 500 g)
  float grams = (float)potVal * (500.0f / 4095.0f);
  return grams;
}

void setup() {
  Serial.begin(115200);
  delay(50);

  // Initialize I2C for MPU6050
  Wire.begin(SDA_PIN, SCL_PIN);
  
  // Initialize MPU6050
  if (!mpu.begin()) {
    Serial.println("Failed to find MPU6050 chip");
    while (1) {
      delay(10);
    }
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  // pins
  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  pinMode(BOX_PIN, INPUT_PULLUP); // button to GND
  pinMode(CAMERA_BTN, INPUT_PULLUP); // button for camera simulation

  setRGB(false,false,false);
  digitalWrite(BUZZER, LOW);

  // sensors
  sensors.begin();
  dht.begin();

  // WiFi
  Serial.print("Connecting to WiFi ");
  Serial.print(ssid);
  WiFi.begin(ssid, password);
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 10000) {
    Serial.print(".");
    delay(500);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected. IP:");
    Serial.println(WiFi.localIP());
    
    // Initialize time for Azure IoT Hub
    configTime(0, 0, "pool.ntp.org");
    
    // Set up MQTT or Azure IoT Hub
    if (useAzureIoT) {
      Serial.println("Using Azure IoT Hub");
      azureConnect();
    } else {
      Serial.println("Using local MQTT broker");
      mqttClient.setServer(mqtt_server, mqtt_port);
      mqttClient.setBufferSize(2048);  // Increase buffer size for larger messages
    }
  } else {
    Serial.println("\nWiFi failed to connect (Wokwi may still allow broker connectivity).");
  }

  // initial baseline weight
  lastWeight = readWeight();
  lastWeightTime = millis();

  // Send startup event
  StaticJsonDocument<256> doc;
  doc["device_id"] = device_id;
  doc["event"] = "startup";
  doc["ip"] = WiFi.localIP().toString();
  String payload; serializeJson(doc, payload);
  // attempt publish (may fail until connected)
  if (WiFi.status() == WL_CONNECTED) {
    reconnect();
    mqttPublish(topic_events.c_str(), payload);
  }
  Serial.println("Setup complete.");
}

void loop() {
  // ensure MQTT/Azure connected
  if (useAzureIoT) {
    azureLoop();  // Handle Azure IoT Hub connection and messages
    if (!isAzureConnected()) {
      reconnect();
    }
  } else {
    if (!mqttClient.connected()) {
      reconnect();
    }
    mqttClient.loop();
  }

  unsigned long now = millis();
  if (now - lastLoop < loopIntervalMs) {
    // but still publish occasional heartbeat every 5s
    if (now - lastHeartbeat > 5000) {
      lastHeartbeat = now;
      if (mqttClient.connected()) {
        StaticJsonDocument<128> h;
        h["device_id"] = device_id;
        h["event"] = "heartbeat";
        h["ts"] = now;
        String hp; serializeJson(h, hp);
        mqttPublish(topic_events.c_str(), hp);
      }
    }
    return;
  }
  lastLoop = now;

  // read sensors
  float weight = readWeight();
  sensors.requestTemperatures();
  float tempC = sensors.getTempCByIndex(0);
  float humidity = dht.readHumidity();
  float dhtTemp = dht.readTemperature();
  int mqRaw = analogRead(MQ2_PIN);
  bool boxOpen = (digitalRead(BOX_PIN) == LOW);
  bool cameraBtnPressed = (digitalRead(CAMERA_BTN) == LOW);
  
  // Read accelerometer data
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  
  // Calculate movement magnitude
  float movement = sqrt(a.acceleration.x * a.acceleration.x + 
                       a.acceleration.y * a.acceleration.y + 
                       a.acceleration.z * a.acceleration.z);
  
  // Check for movement
  bool isMoving = (movement > movementThreshold);
  
  // Simulate face recognition when button is pressed
  static bool faceRecognized = false;
  static unsigned long lastFaceCheck = 0;
  if (cameraBtnPressed && (millis() - lastFaceCheck > faceRecognitionTimeout)) {
    faceRecognized = !faceRecognized; // Toggle for simulation
    lastFaceCheck = millis();
    if (faceRecognized) {
      Serial.println("Face recognized: Authorized user");
      setRGB(false, true, false); // Green for authorized
    } else {
      Serial.println("Face not recognized: Unauthorized user");
      setRGB(true, false, false); // Red for unauthorized
      beep(200); // Short beep for unauthorized
    }
  }

  Serial.printf("W: %.1f g, TempDS18: %.2f C, DHT_T: %.2f C, H: %.2f %% , MQ: %d, Open:%d\n",
                weight, tempC, dhtTemp, humidity, mqRaw, boxOpen);

  // publish telemetry
  StaticJsonDocument<512> tdoc; // Increased size for additional sensors
  tdoc["device_id"] = device_id;
  tdoc["ts"] = now;
  tdoc["weight_g"] = weight;
  tdoc["temp_ds18"] = tempC;
  tdoc["temp_dht"] = dhtTemp;
  
  // Add accelerometer data
  JsonObject accel = tdoc.createNestedObject("accelerometer");
  accel["x"] = a.acceleration.x;
  accel["y"] = a.acceleration.y;
  accel["z"] = a.acceleration.z;
  accel["movement"] = movement;
  accel["is_moving"] = isMoving;
  
  // Add camera/face recognition status
  tdoc["face_recognized"] = faceRecognized;
  tdoc["camera_btn_pressed"] = cameraBtnPressed;
  tdoc["humidity"] = humidity;
  tdoc["mq_raw"] = mqRaw;
  tdoc["box_open"] = boxOpen;
  String tpayload; serializeJson(tdoc, tpayload);
  mqttPublish(topic_telemetry.c_str(), tpayload);

  // detect consumption / sharing
  float delta = lastWeight - weight; // positive if weight decreased
  unsigned long dt = now - lastWeightTime;

  if (boxOpen && delta > weightThresholdConsume && dt < 60000) {
    StaticJsonDocument<256> edoc;
    edoc["device_id"] = device_id;
    edoc["event"] = "consumption";
    edoc["delta_g"] = delta;
    edoc["weight_after_g"] = weight;
    edoc["ts"] = now;
    String ep; serializeJson(edoc, ep);
    mqttPublish(topic_events.c_str(), ep);
    setRGB(true, false, true);
    delay(200);
    setRGB(false,false,false);
  }

  if (delta > 0) {
    float pct = (lastWeight > 0.1) ? (delta / lastWeight * 100.0) : 0.0;
    if (pct >= weightThresholdSharePct && dt <= shareWindowMs && boxOpen) {
      StaticJsonDocument<256> sdoc;
      sdoc["device_id"] = device_id;
      sdoc["event"] = "sharing_detected";
      sdoc["drop_g"] = delta;
      sdoc["drop_pct"] = pct;
      sdoc["ts"] = now;
      String sp; serializeJson(sdoc, sp);
      mqttPublish(topic_events.c_str(), sp);

      for (int i=0;i<3;i++){
        setRGB(true,false,false);
        beep(200);
        delay(200);
        setRGB(false,false,false);
        delay(150);
      }
    }
  }

  // Safety checks
  bool safetyIssue = false;
  String safetyReason = "";
  if (!isnan(tempC) && tempC >= unsafeTempC) {
    safetyIssue = true;
    safetyReason += "temperature;";
  }
  if (mqRaw >= unsafeGasLevel) {
    safetyIssue = true;
    safetyReason += "gas;";
  }
  if (!isnan(humidity) && humidity > 90) {
    safetyIssue = true;
    safetyReason += "humidity;";
  }

  if (safetyIssue) {
    StaticJsonDocument<256> sdoc;
    sdoc["device_id"] = device_id;
    sdoc["event"] = "food_safety_alert";
    sdoc["reason"] = safetyReason;
    sdoc["temp_ds18"] = tempC;
    sdoc["mq_raw"] = mqRaw;
    sdoc["humidity"] = humidity;
    sdoc["ts"] = now;
    String sp; serializeJson(sdoc, sp);
    mqttPublish(topic_events.c_str(), sp);

    setRGB(true,true,false);
    for (int i=0;i<2;i++){
      beep(150); delay(200);
    }
    setRGB(false,false,false);
  }

  // update baseline if changed or after stable interval
  if (abs(delta) > 0.01 || dt > 30000) {
    lastWeight = weight;
    lastWeightTime = now;
  }
}
