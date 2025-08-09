#include "azure_iot.h"
#include <WiFi.h>

// WiFi and MQTT clients
extern WiFiClientSecure secureEspClient; // Use the client from the main sketch
extern PubSubClient mqttClient;          // Use the client from the main sketch

// Connection state
bool connected = false;
unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECTION_DELAY = 10000; // 10 seconds

// MQTT Callback for handling direct methods from Azure
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Handle incoming messages and direct methods
  char message[length + 1];
  memcpy(message, payload, length);
  message[length] = '\0';
  
  Serial.print("Message arrived on topic [");
  Serial.print(topic);
  Serial.println("]");
  
  // Handle direct methods (e.g., from Azure Portal)
  if (strstr(topic, "$iothub/methods/POST/")) {
    Serial.println("Direct Method received.");
    // Add logic here to handle commands like rebooting, changing settings, etc.
  }
  // Handle device twin updates
  else if (strstr(topic, "$iothub/twin/res/")) {
    Serial.println("Device Twin response received.");
    // Add logic here to process desired properties from the twin.
  }
}

// Connect to Azure IoT Hub using SAS Token
bool azureConnect(const char* sasToken) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected");
    return false;
  }

  // Format the username as required by Azure IoT Hub
  String username = String(IOTHUB_HOSTNAME) + "/" + String(DEVICE_ID) + "/?api-version=2021-04-12";

  Serial.println("Attempting Azure IoT Hub connection...");
  Serial.printf("Client ID: %s\n", DEVICE_ID);
  Serial.printf("Username: %s\n", username.c_str());
  
  // The SAS token is used as the password
  if (mqttClient.connect(DEVICE_ID, username.c_str(), sasToken)) {
      Serial.println("SUCCESS: Connected to Azure IoT Hub!");
      connected = true;

      // Subscribe to topics for direct methods and device twin updates
      mqttClient.subscribe(AZURE_IOT_HUB_METHODS_POST);
      mqttClient.subscribe(AZURE_IOT_HUB_TWIN_UPDATE);
      
      // Request the device twin properties from Azure
      mqttClient.publish(AZURE_IOT_HUB_TWIN_GET, "");
      Serial.println("Subscribed to methods and twin topics.");
      
      return true;
  } else {
      Serial.print("FAILED to connect to Azure IoT Hub, rc=");
      Serial.print(mqttClient.state());
      
      // Provide more helpful error messages
      switch (mqttClient.state()) {
        case MQTT_CONNECT_BAD_PROTOCOL:
          Serial.println(" -> Bad protocol");
          break;
        case MQTT_CONNECT_BAD_CLIENT_ID:
          Serial.println(" -> Bad client ID");
          break;
        case MQTT_CONNECT_UNAVAILABLE:
          Serial.println(" -> Service unavailable");
          break;
        case MQTT_CONNECT_BAD_CREDENTIALS:
          Serial.println(" -> Bad credentials (Check your SAS Token)");
          break;
        case MQTT_CONNECT_UNAUTHORIZED:
          Serial.println(" -> Unauthorized");
          break;
        default:
          Serial.println(" -> Unknown error");
          break;
      }
      connected = false;
      return false;
  }
}

// Disconnect from Azure IoT Hub
void azureDisconnect() {
  mqttClient.disconnect();
  connected = false;
  Serial.println("Disconnected from Azure IoT Hub");
}

// Publish message to the standard telemetry topic
bool azurePublish(const char* topic, const char* payload) {
  if (!isAzureConnected()) {
    Serial.println("Cannot publish, not connected to Azure.");
    return false;
  }
  
  bool result = mqttClient.publish(topic, payload);
  if (!result) {
    Serial.println("Failed to publish message!");
  }
  return result;
}

// Maintain connection and process incoming messages
void azureLoop() {
  if (!isAzureConnected()) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > RECONNECTION_DELAY) {
      lastReconnectAttempt = now;
      Serial.println("Connection lost. Reconnecting to Azure...");
      // The main sketch.ino will handle calling reconnect()
    }
  } else {
    mqttClient.loop();
  }
}

// Check if connected to Azure IoT Hub
bool isAzureConnected() {
  return connected && mqttClient.connected();
}
