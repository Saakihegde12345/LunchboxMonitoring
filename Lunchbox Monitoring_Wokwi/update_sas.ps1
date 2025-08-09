# Variables
$hubName = "LunchboxMonitoring"   # Your IoT Hub name (NOT hostname)
$deviceId = "lunchbox_esp32_sim" # Your device ID
$filePath = "azure_iot.h"   # Path to your header file
$duration = 86400            # Token validity in seconds (1 hour)

# Generate SAS Token using Azure CLI
$sasToken = az iot hub generate-sas-token --hub-name $hubName --device-id $deviceId --duration $duration --output tsv

# Read file, replace SAS_TOKEN line, and save
(Get-Content $filePath) -replace '(?<=#define SAS_TOKEN ").*?(?=")', $sasToken | Set-Content $filePath

Write-Host "✅ SAS token updated in $filePath"
