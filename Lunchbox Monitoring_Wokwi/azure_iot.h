#ifndef AZURE_IOT_H
#define AZURE_IOT_H

#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

// Azure IoT Hub Settings - Replace with your values
#define IOTHUB_HOSTNAME "LunchboxMonitoring.azure-devices.net"  // Replace with your IoT Hub name
#define DEVICE_ID "lunchbox_esp32"

// MQTT Topics
#define AZURE_IOT_HUB_TELEMETRY_TOPIC "devices/" DEVICE_ID "/messages/events/"
#define AZURE_IOT_HUB_METHODS_POST "$iothub/methods/POST/#"
#define AZURE_IOT_HUB_TWIN_UPDATE "$iothub/twin/res/#"
#define AZURE_IOT_HUB_TWIN_GET "$iothub/twin/GET/?$rid=1"


// SSL/TLS Configuration
const char* root_ca = \
"-----BEGIN CERTIFICATE-----\n" \
"MIIDdzCCAl+gAwIBAgIEAgAAuTANBgkqhkiG9w0BAQUFADBaMQswCQYDVQQGEwJJ\n" \
"....\n" \
"-----END CERTIFICATE-----";

// Function declarations
bool azureConnect(const char* sasToken);
void azureDisconnect();
bool azurePublish(const char* topic, const char* payload);
void azureLoop();
bool isAzureConnected();
void mqttCallback(char* topic, byte* payload, unsigned int length);


#endif
