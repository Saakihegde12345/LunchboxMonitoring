#include "azure_iot.h"
#include <WiFi.h>
#include <base64.h>
#include <ArduinoJson.h>
#include <mbedtls/md.h>

// WiFi and MQTT clients
WiFiClientSecure wifiClient;
PubSubClient mqttClient(wifiClient);

// Connection state
bool connected = false;
unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECTION_DELAY = 5000; // 5 seconds

// Extract values from connection string
String iotHubHost;
String deviceId;
String deviceKey;

// Parse connection string and extract credentials
void parseConnectionString() {
  String connStr = String(CONNECTION_STRING);
  int hostStart = connStr.indexOf("HostName=") + 9;
  int hostEnd = connStr.indexOf(";", hostStart);
  iotHubHost = connStr.substring(hostStart, hostEnd);
  
  int deviceStart = connStr.indexOf("DeviceId=") + 9;
  int deviceEnd = connStr.indexOf(";", deviceStart);
  deviceId = connStr.substring(deviceStart, deviceEnd);
  
  int keyStart = connStr.indexOf("SharedAccessKey=") + 16;
  deviceKey = connStr.substring(keyStart);
}

// URL encode a string
String urlEncode(const char* msg) {
  const char *hex = "0123456789abcdef";
  String encodedMsg = "";
  while (*msg != '\0') {
    if (('a' <= *msg && *msg <= 'z') ||
        ('A' <= *msg && *msg <= 'Z') ||
        ('0' <= *msg && *msg <= '9') ||
        *msg == '-' || *msg == '_' || *msg == '.' || *msg == '~') {
      encodedMsg += *msg;
    } else {
      encodedMsg += '%';
      encodedMsg += hex[*msg >> 4];
      encodedMsg += hex[*msg & 15];
    }
    msg++;
  }
  return encodedMsg;
}

// Generate SAS token
String generateSasToken(String uri, String key, String policyName, int expiryInSeconds) {
  String stringToSign = urlEncode(uri.c_str()) + "\n" + String(expiryInSeconds);
  
  // Use mbedtls to generate the HMAC-SHA256
  const size_t hmacLength = 32;
  unsigned char hmacResult[hmacLength];
  
  const mbedtls_md_info_t *md_info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (md_info == NULL) {
    Serial.println("Failed to get MD info for SHA-256");
    return "";
  }
  
  if (mbedtls_md_hmac(md_info, 
                     (const unsigned char*)key.c_str(), key.length(),
                     (const unsigned char*)stringToSign.c_str(), stringToSign.length(),
                     hmacResult) != 0) {
    Serial.println("Failed to generate HMAC-SHA256");
    return "";
  }
  
  // Base64 encode the HMAC result
  String signature = base64::encode(hmacResult, hmacLength);
  
  // Construct the SAS token
  String token = "SharedAccessSignature sr=" + uri + "&sig=" + urlEncode(signature.c_str()) + "&se=" + String(expiryInSeconds);
  if (policyName.length() > 0) {
    token += "&skn=" + policyName;
  }
  
  return token;
}

// MQTT Callback for handling direct methods and device twin updates
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Handle incoming messages and direct methods
  char message[length + 1];
  memcpy(message, payload, length);
  message[length] = '\0';
  
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(message);
  
  // Handle direct methods
  if (strstr(topic, "$iothub/methods/POST/")) {
    // Extract method name from topic
    char* methodStart = strrchr(topic, '/') + 1;
    char methodName[32];
    strncpy(methodName, methodStart, sizeof(methodName));
    methodName[sizeof(methodName) - 1] = '\0';
    
    // Create response topic
    char responseTopic[128];
    const char* ridPtr = strstr(topic, "$rid=");
    if (ridPtr) {
      ridPtr += 5; // Move past "$rid="
      const char* qmarkPtr = strchr(topic, '?');
      if (qmarkPtr && qmarkPtr > ridPtr) {
        int ridLen = qmarkPtr - ridPtr;
        snprintf(responseTopic, sizeof(responseTopic), "$iothub/methods/res/200/?$rid=%.*s", 
                ridLen, ridPtr);
      }
    }
    
    // Process the method
    DynamicJsonDocument doc(1024);
    deserializeJson(doc, message);
    
    DynamicJsonDocument response(256);
    response["status"] = "success";
    response["method"] = methodName;
    
    // Add method-specific response
    if (strcmp(methodName, "getDeviceInfo") == 0) {
      response["deviceType"] = "SmartLunchbox";
      response["firmwareVersion"] = "1.0.0";
    }
    
    String responseMsg;
    serializeJson(response, responseMsg);
    
    mqttClient.publish(responseTopic, responseMsg.c_str());
  }
  // Handle device twin updates
  else if (strstr(topic, "$iothub/twin/res/")) {
    // Process twin updates
    DynamicJsonDocument doc(1024);
    deserializeJson(doc, message);
    
    if (doc.containsKey("desired")) {
      // Handle desired properties update
      JsonObject desired = doc["desired"];
      if (desired.containsKey("telemetryInterval")) {
        // Update telemetry interval
        int newInterval = desired["telemetryInterval"];
        // Update your device's telemetry interval here
        Serial.print("Telemetry interval updated to: ");
        Serial.println(newInterval);
      }
    }
  }
}

// Connect to Azure IoT Hub
bool azureConnect() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected");
    return false;
  }
  
  // Set time via NTP for certificate validation
  configTime(0, 0, "pool.ntp.org");
  
  // Set root CA certificate
  wifiClient.setCACert(root_ca);
  
  // Set MQTT server
  mqttClient.setServer(IOTHUB_HOSTNAME, 8883);
  mqttClient.setCallback(mqttCallback);
  
  // Generate client ID
  String clientId = String(DEVICE_ID) + "-" + String(random(0xffff), HEX);
  
  // For Wokwi, we'll use a simplified connection
  // In a real scenario, you would use the SAS token for authentication
  if (mqttClient.connect(clientId.c_str())) {
    Serial.println("Connected to Azure IoT Hub");
    
    // In Wokwi, we'll just log the connection
    Serial.println("Simulated Azure IoT Hub connection successful");
    connected = true;
    return true;
  } else {
    Serial.print("Failed to connect to Azure IoT Hub, rc=");
    Serial.println(mqttClient.state());
    return false;
  }
}

// Disconnect from Azure IoT Hub
void azureDisconnect() {
  mqttClient.disconnect();
  connected = false;
  Serial.println("Disconnected from Azure IoT Hub");
}

// Publish message to Azure IoT Hub
bool azurePublish(const char* topic, const char* payload) {
  if (!connected) {
    return false;
  }
  
  bool result = mqttClient.publish(topic, payload);
  if (!result) {
    Serial.println("Failed to publish message");
    connected = false;
  }
  return result;
}

// Process MQTT messages
void azureLoop() {
  if (!connected) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > RECONNECTION_DELAY) {
      lastReconnectAttempt = now;
      if (azureConnect()) {
        lastReconnectAttempt = 0;
      }
    }
  } else {
    mqttClient.loop();
  }
}

// Check if connected to Azure IoT Hub
bool isAzureConnected() {
  return connected && mqttClient.connected();
}
