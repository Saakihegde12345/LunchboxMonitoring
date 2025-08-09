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
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Set to false to use a local MQTT broker instead of Azure
const bool useAzureIoT = true;

// --- Local MQTT Broker Settings ---
const char* mqtt_server = "test.mosquitto.org";
const uint16_t mqtt_port = 1883;
const char* device_id = "lunchbox_esp32_sim";
String topic_telemetry = String("lunchbox/") + device_id + "/telemetry";
String topic_events = String("lunchbox/") + device_id + "/events";

// ===== PINS =====
#define POT_PIN 35
#define ONEWIRE_PIN 25
#define DHTPIN 26
#define MQ2_PIN 34
#define BOX_PIN 27
#define LED_R 14
#define LED_G 12
#define LED_B 13
#define BUZZER 15
#define SDA_PIN 21
#define SCL_PIN 22
#define CAMERA_BTN 4

// ===== SENSORS =====
OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);
DHT dht(DHTPIN, DHT22);
Adafruit_MPU6050 mpu;

// ===== MQTT / WiFi =====
WiFiClient espClient;
WiFiClientSecure secureEspClient; // For Azure
PubSubClient mqttClient;

// ===== State & thresholds =====
float lastWeight = 0.0;
unsigned long lastWeightTime = 0;
const float weightThresholdConsume = 5.0;
const float weightThresholdSharePct = 35.0;
const unsigned long shareWindowMs = 8000;
const float unsafeTempC = 60.0;
const int unsafeGasLevel = 3000;
const int loopIntervalMs = 2000;
const float movementThreshold = 2.0;
const int faceRecognitionTimeout = 5000;

unsigned long lastLoop = 0;
unsigned long lastHeartbeat = 0;

// ===== Helpers =====
void setRGB(bool r, bool g, bool b) {
  digitalWrite(LED_R, r ? LOW : HIGH);
  digitalWrite(LED_G, g ? LOW : HIGH);
  digitalWrite(LED_B, b ? LOW : HIGH);
}

void beep(int ms) {
  digitalWrite(BUZZER, HIGH);
  delay(ms);
  digitalWrite(BUZZER, LOW);
}

void mqttPublish(const String &topic, const String &payload) {
  if (mqttClient.connected()) {
    mqttClient.publish(topic.c_str(), payload.c_str());
  } else {
    Serial.println("MQTT not connected, cannot publish.");
  }
}

void reconnect() {
  if (useAzureIoT) {
    if (!isAzureConnected()) {
      Serial.println("Attempting to connect to Azure IoT Hub...");
      // IMPORTANT: You must get a new SAS token here.
      // This is a placeholder for your token generation logic.
      const char* sasToken = "PASTE_YOUR_NEW_SAS_TOKEN_HERE";
      if (!azureConnect(sasToken)) {
        Serial.println("Failed to connect to Azure IoT Hub, will retry...");
      }
    }
  } else {
    if (!mqttClient.connected()) {
      Serial.print("Connecting to MQTT broker...");
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
}

float readWeight() {
  int potVal = analogRead(POT_PIN);
  float grams = (float)potVal * (500.0f / 4095.0f);
  return grams;
}

void setup() {
  Serial.begin(115200);
  delay(50);

  Wire.begin(SDA_PIN, SCL_PIN);
  if (!mpu.begin()) {
    Serial.println("Failed to find MPU6050 chip");
    while (1) {
      delay(10);
    }
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  pinMode(BOX_PIN, INPUT_PULLUP);
  pinMode(CAMERA_BTN, INPUT_PULLUP);

  setRGB(false, false, false);
  digitalWrite(BUZZER, LOW);

  sensors.begin();
  dht.begin();

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
    configTime(0, 0, "pool.ntp.org");

    if (useAzureIoT) {
        secureEspClient.setCACert(root_ca);
        mqttClient.setClient(secureEspClient);
        mqttClient.setServer(IOTHUB_HOSTNAME, 8883);
        mqttClient.setCallback(mqttCallback);
    } else {
        mqttClient.setClient(espClient);
        mqttClient.setServer(mqtt_server, mqtt_port);
    }
     mqttClient.setBufferSize(2048);
  } else {
    Serial.println("\nWiFi failed to connect.");
  }

  lastWeight = readWeight();
  lastWeightTime = millis();
  reconnect(); // Initial connection attempt
}


void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi disconnected. Attempting to reconnect...");
        WiFi.begin(ssid, password);
        delay(5000);
        return;
    }

    if (useAzureIoT) {
        azureLoop();
    } else {
        if (!mqttClient.connected()) {
            reconnect();
        }
        mqttClient.loop();
    }


  unsigned long now = millis();
  if (now - lastLoop < loopIntervalMs) {
    if (now - lastHeartbeat > 5000) {
      lastHeartbeat = now;
      if (mqttClient.connected()) {
        StaticJsonDocument<128> h;
        h["device_id"] = device_id;
        h["event"] = "heartbeat";
        h["ts"] = now;
        String hp; serializeJson(h, hp);
        mqttPublish(topic_events, hp);
      }
    }
    return;
  }
  lastLoop = now;

  float weight = readWeight();
  sensors.requestTemperatures();
  float tempC = sensors.getTempCByIndex(0);
  float humidity = dht.readHumidity();
  float dhtTemp = dht.readTemperature();
  int mqRaw = analogRead(MQ2_PIN);
  bool boxOpen = (digitalRead(BOX_PIN) == LOW);
  bool cameraBtnPressed = (digitalRead(CAMERA_BTN) == LOW);

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  float movement = sqrt(a.acceleration.x * a.acceleration.x + a.acceleration.y * a.acceleration.y + a.acceleration.z * a.acceleration.z);
  bool isMoving = (movement > movementThreshold);

  static bool faceRecognized = false;
  static unsigned long lastFaceCheck = 0;
  if (cameraBtnPressed && (millis() - lastFaceCheck > faceRecognitionTimeout)) {
    faceRecognized = !faceRecognized;
    lastFaceCheck = millis();
    if (faceRecognized) {
      Serial.println("Face recognized: Authorized user");
      setRGB(false, true, false);
    } else {
      Serial.println("Face not recognized: Unauthorized user");
      setRGB(true, false, false);
      beep(200);
    }
  }

  Serial.printf("W: %.1f g, TempDS18: %.2f C, DHT_T: %.2f C, H: %.2f %% , MQ: %d, Open:%d\n",
                weight, tempC, dhtTemp, humidity, mqRaw, boxOpen);

  StaticJsonDocument<512> tdoc;
  tdoc["device_id"] = device_id;
  tdoc["ts"] = now;
  tdoc["weight_g"] = weight;
  tdoc["temp_ds18"] = tempC;
  tdoc["temp_dht"] = dhtTemp;
  JsonObject accel = tdoc.createNestedObject("accelerometer");
  accel["x"] = a.acceleration.x;
  accel["y"] = a.acceleration.y;
  accel["z"] = a.acceleration.z;
  accel["movement"] = movement;
  accel["is_moving"] = isMoving;
  tdoc["face_recognized"] = faceRecognized;
  tdoc["camera_btn_pressed"] = cameraBtnPressed;
  tdoc["humidity"] = humidity;
  tdoc["mq_raw"] = mqRaw;
  tdoc["box_open"] = boxOpen;
  String tpayload; serializeJson(tdoc, tpayload);

  if(useAzureIoT) {
      mqttPublish(AZURE_IOT_HUB_TELEMETRY_TOPIC, tpayload);
  } else {
      mqttPublish(topic_telemetry, tpayload);
  }


  float delta = lastWeight - weight;
  unsigned long dt = now - lastWeightTime;
  if (boxOpen && delta > weightThresholdConsume && dt < 60000) {
    StaticJsonDocument<256> edoc;
    edoc["device_id"] = device_id;
    edoc["event"] = "consumption";
    edoc["delta_g"] = delta;
    edoc["weight_after_g"] = weight;
    edoc["ts"] = now;
    String ep; serializeJson(edoc, ep);
    mqttPublish(topic_events, ep);
    setRGB(true, false, true);
    delay(200);
    setRGB(false, false, false);
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
      mqttPublish(topic_events, sp);

      for (int i = 0; i < 3; i++) {
        setRGB(true, false, false);
        beep(200);
        delay(200);
        setRGB(false, false, false);
        delay(150);
      }
    }
  }

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
    mqttPublish(topic_events, sp);

    setRGB(true, true, false);
    for (int i = 0; i < 2; i++) {
      beep(150);
      delay(200);
    }
    setRGB(false, false, false);
  }

  if (abs(delta) > 0.01 || dt > 30000) {
    lastWeight = weight;
    lastWeightTime = now;
  }
}
