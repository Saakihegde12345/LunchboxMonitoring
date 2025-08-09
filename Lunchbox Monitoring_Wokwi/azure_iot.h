#ifndef AZURE_IOT_H
#define AZURE_IOT_H

#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

// Azure IoT Hub Settings - Replace with your values
#define IOTHUB_HOSTNAME "LunchboxMonitoring.azure-devices.net"  // Replace with your IoT Hub name
#define DEVICE_ID "lunchbox_esp32"

// Primary connection string from Azure IoT Hub
// Format: HostName=<iothub_host_name>;DeviceId=<device_id>;SharedAccessKey=<device_key>
#define CONNECTION_STRING "HostName=LunchboxMonitoring.azure-devices.net;DeviceId=lunchbox_esp32;SharedAccessKey=SharedAccessSignature sr=LunchboxMonitoring.azure-devices.net%2Fdevices%2Flunchbox_esp32_sim&sig=3zA%2FMzIDFaDc9%2B3Mu4m6wbAI55lm9xR1CKIIEzvns34%3D&se=1754822645"

// MQTT Topics
#define AZURE_IOT_HUB_TOPIC "devices/" DEVICE_ID "/messages/events/"
#define AZURE_IOT_HUB_METHODS "$iothub/methods/POST/#"

// SSL/TLS Configuration
const char* root_ca = \
"-----BEGIN CERTIFICATE-----\n" \
"MIIDdzCCAl+gAwIBAgIEAgAAuTANBgkqhkiG9w0BAQUFADBaMQswCQYDVQQGEwJJ\n" \
"... [truncated for brevity] ...\n" \
"-----END CERTIFICATE-----";

// Function declarations
bool azureConnect();
void azureDisconnect();
bool azurePublish(const char* topic, const char* payload);
void azureLoop();
bool isAzureConnected();

// Helper functions for SAS token generation
String generateSasToken(String uri, String key, String policyName, int expiryInSeconds);
String urlEncode(const char* msg);

#endif
