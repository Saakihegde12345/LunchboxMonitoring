/********************************************************
 * Step 9 (Enhanced v2): Calibration Persistence + Smoothing + Slim Payload
 ********************************************************/
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Preferences.h>
#include <esp_system.h>
#include <time.h>

/* -------- User Config -------- */
bool        USE_TUNNEL    = true;
const char* TUNNEL_HOST   = "baghdad-dosage-architects-colors.trycloudflare.com";
const uint16_t TUNNEL_PORT= 443;
const char*  LAN_HOST     = "192.168.0.157";
const uint16_t LAN_PORT   = 8000;
const char* INGEST_PATH    = "/api/ingest/device/";
const char* DEVICE_API_KEY = "625dc0bb-bfcb-4887-a194-2c20546b48bd";
const char* WIFI_SSID      = "Wokwi-GUEST";
const char* WIFI_PASS      = "";

/* Recalibration control */
bool FORCE_RECAL = false;

/* Sensors */
#define DHTPIN 26
#define DHTTYPE DHT22
#define GAS_PIN 34
// New sensors: HC-SR04 Ultrasonic (Proximity) and PIR Motion
#define PROX_TRIG_PIN 12
#define PROX_ECHO_PIN 14
#define PIR_PIN       27
DHT dht(DHTPIN, DHTTYPE);

/* Gas calibration + mapping */
const float PPM_MIN = 0.1f;
const float PPM_MAX = 100000.f;
const int   MIN_SAMPLES = 120;
const int   STABLE_CYCLES_MAX = 25;
const int   SAMPLE_BLOCK = 8;
const int   SAMPLE_DELAY_MS = 4;

/* Timing */
const unsigned long DHT_INTERVAL_MS   = 2500;
const unsigned long GAS_POLL_MS       = 300;
const unsigned long PRINT_INTERVAL_MS = 5000;
const unsigned long MIN_POST_INTERVAL = 2000;
const unsigned long FORCE_INTERVAL    = 25000;

/* Thresholds */
const float TEMP_DELTA_MIN       = 0.2f;
const float HUMI_DELTA_MIN       = 1.0f;
const float GAS_RATIO_DELTA_MIN  = 0.10f;   // fraction of span
const float GAS_PPM_DELTA_MIN    = 500.0f;  // absolute ppm change
const float PROX_DELTA_MIN       = 2.0f;    // cm change to trigger send
/* Smoothing / clamping */
const float GAS_PPM_EMA_ALPHA    = 0.30f;
const float PPM_DISPLAY_MIN      = 1.0f;
const float PPM_DISPLAY_MAX      = 5000.0f; // compress extremes

/* DHT outlier guard */
const float TEMP_SPIKE_MAX_DIFF  = 15.0f;
const float HUMI_SPIKE_MAX_DIFF  = 20.0f;

/* State */
float dhtTemp = NAN, dhtHumi = NAN;
float lastGoodTemp = NAN, lastGoodHumi = NAN;
float lastSentTemp = NAN, lastSentHumi = NAN, lastSentGasPPM = NAN;
float lastSentProx = NAN;
int   lastSentMotion = -1;
float gasRawMin = NAN, gasRawMax = NAN;
bool  gasMaxLocked = false;
int   gasStableCount = 0;
bool  usedStoredCalibration = false;
bool  gasMetaSent = false;
float gasPpmEma = NAN;

unsigned long lastGasPoll = 0;
unsigned long lastDhtPoll = 0;
unsigned long lastJson    = 0;
unsigned long lastPost    = 0;

// Bump JSON buffer to ensure all readings (incl. prox & motion) fit even when gas meta fields are present
// Previously 768 was marginal and could drop the last-added objects under memory pressure.
StaticJsonDocument<1536> doc;

/* Persistence */
Preferences prefs;
const char* NVS_NAMESPACE = "gascal";
const uint16_t CAL_VERSION = 1;

uint32_t simpleChecksum(float a, float b) {
  uint32_t* pa = (uint32_t*)&a;
  uint32_t* pb = (uint32_t*)&b;
  uint32_t c = *pa ^ (*pb << 1);
  c ^= 0xA5A5A5A5;
  return c;
}

bool loadCalibration() {
  // Try read-only first; if namespace doesn't exist yet, open RW to create it
  if(!prefs.begin(NVS_NAMESPACE, true)){
    Serial.println("[CAL] NVS RO open fail; retry RW to create namespace");
    if(!prefs.begin(NVS_NAMESPACE, false)){
      Serial.println("[CAL] NVS RW open fail");
      return false;
    }
  }
  uint16_t ver = prefs.getUShort("ver",0);
  float sMin = prefs.getFloat("min",NAN);
  float sMax = prefs.getFloat("max",NAN);
  uint32_t crc = prefs.getUInt("crc",0);
  prefs.end();
  // Nothing stored yet
  if(ver == 0){ Serial.println("[CAL] No calibration stored yet"); return false; }
  // Firmware schema changed
  if(ver != CAL_VERSION){
    Serial.printf("[CAL] Version mismatch (stored %u != fw %u); recalibrating\n", ver, CAL_VERSION);
    return false;
  }
  // If max is missing or span invalid, treat as incomplete (user must finish the MAX lock step)
  if(!(sMin>=0 && sMax<=4095 && sMax>sMin+29)){
    Serial.println("[CAL] Stored calibration incomplete/invalid; recalibrate");
    return false;
  }
  // Verify checksum on valid span only
  if(crc != simpleChecksum(sMin,sMax)){ Serial.println("[CAL] CRC mismatch; recalibrating"); return false; }
  gasRawMin = sMin; gasRawMax = sMax; gasMaxLocked = true; usedStoredCalibration = true;
  Serial.printf("[CAL] Loaded min=%.1f max=%.1f\n", gasRawMin, gasRawMax);
  return true;
}

void saveCalibration() {
  if(!gasMaxLocked) return;
  if(!prefs.begin(NVS_NAMESPACE,false)){ Serial.println("[CAL] NVS RW open fail"); return; }
  prefs.putUShort("ver", CAL_VERSION);
  prefs.putFloat("min", gasRawMin);
  prefs.putFloat("max", gasRawMax);
  prefs.putUInt("crc", simpleChecksum(gasRawMin, gasRawMax));
  prefs.end();
  Serial.println("[CAL] Saved calibration");
}

/* Serial helper commands (always available while running)
   - 'S' : show stored calibration (ver/min/max/crc)
   - 'E' : software reset (ESP.restart) -> preserves NVS, like EN button
   - 'X' : clear calibration namespace, then restart
   - 'R' : force recalibration on next boot (clears cal + restart)
*/
void printStoredCal(){
  if(!prefs.begin(NVS_NAMESPACE, true)){
    Serial.println("[CAL] NVS open fail (RO) while printing");
    return;
  }
  uint16_t ver = prefs.getUShort("ver",0);
  float sMin = prefs.getFloat("min",NAN);
  float sMax = prefs.getFloat("max",NAN);
  uint32_t crc = prefs.getUInt("crc",0);
  prefs.end();
  Serial.printf("[CAL] Stored ver=%u min=%.1f max=%.1f crc=0x%08lx\n", ver, sMin, sMax, (unsigned long)crc);
}

void handleSerialCommands(){
  while(Serial.available()>0){
    char c = Serial.read();
    if(c=='\n' || c=='\r') continue;
    if(c=='S' || c=='s'){
      printStoredCal();
    } else if(c=='E' || c=='e'){
      Serial.println("[CAL] SW reset via esp_restart()");
      delay(100);
      esp_restart();
    } else if(c=='X' || c=='x' || c=='R' || c=='r'){
      if(prefs.begin(NVS_NAMESPACE,false)){
        prefs.clear();
        prefs.end();
      }
  Serial.println(c=='R'||c=='r' ? "[CAL] Cleared cal; forcing recalibration on restart" : "[CAL] Cleared cal; restarting");
  delay(100);
  esp_restart();
    } else {
      Serial.printf("[CMD] Unknown '%c' (use S=show, E=reset, X=clear+reset, R=recal+reset)\n", c);
    }
  }
}

/* Time */
bool timeSynced=false;
String isoTimestampUTC(){
  if(!timeSynced) return String();
  time_t now=time(nullptr); if(now<1700000000) return String();
  struct tm* t=gmtime(&now); char buf[25];
  strftime(buf,sizeof(buf),"%Y-%m-%dT%H:%M:%SZ",t);
  return String(buf);
}
void syncTime(){
  configTime(0,0,"pool.ntp.org","time.nist.gov");
  Serial.print("Time sync");
  for(int i=0;i<40;i++){ time_t now=time(nullptr); if(now>1700000000){ timeSynced=true; Serial.println(" OK"); return; } Serial.print('.'); delay(300); }
  Serial.println(" fail");
}

/* Helpers */
float readGasBlockAvg(){
  long sum=0;
  for(int i=0;i<SAMPLE_BLOCK;i++){ sum+=analogRead(GAS_PIN); delay(SAMPLE_DELAY_MS); }
  return (float)sum/SAMPLE_BLOCK;
}

void captureGasMin(){
  float acc=0;
  for(int i=0;i<MIN_SAMPLES;i++) acc+=readGasBlockAvg();
  gasRawMin = acc/MIN_SAMPLES;
  Serial.printf("Gas MIN captured rawMin=%.1f\n", gasRawMin);
  Serial.println("Move slider HIGH until 'Gas MAX locked'.");
}

void considerLockMax(float raw){
  if(gasMaxLocked) return;
  if(isnan(gasRawMax) || raw>gasRawMax){ gasRawMax=raw; gasStableCount=0; }
  else gasStableCount++;
  if(!isnan(gasRawMax) && gasStableCount>=STABLE_CYCLES_MAX){
    if(gasRawMax - gasRawMin < 30){ Serial.println("[WARN] Span too small; raise slider."); gasStableCount=0; return; }
    gasMaxLocked=true;
    Serial.printf("Gas MAX locked rawMax=%.1f span=%.1f\n",gasRawMax, gasRawMax-gasRawMin);
    saveCalibration();
  }
}

float linearRatio(float raw){
  if(!gasMaxLocked || gasRawMax <= gasRawMin+1) return NAN;
  float r=(raw-gasRawMin)/(gasRawMax-gasRawMin);
  if(r<0) r=0; if(r>1) r=1;
  return r;
}

float mapGasToPPM(float raw){
  if(!gasMaxLocked || isnan(raw)) return NAN;
  float r=linearRatio(raw);
  if(isnan(r)) return NAN;
  float logMin=log10(PPM_MIN), logMax=log10(PPM_MAX);
  float ppm = pow(10, logMin + r*(logMax-logMin));
  if(ppm<PPM_DISPLAY_MIN) ppm=PPM_DISPLAY_MIN;
  if(ppm>PPM_DISPLAY_MAX) ppm=PPM_DISPLAY_MAX;
  return ppm;
}

void connectWiFi(){
  if(WiFi.status()==WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi connecting");
  unsigned long start=millis();
  while(WiFi.status()!=WL_CONNECTED && millis()-start<15000){ Serial.print('.'); delay(500); }
  if(WiFi.status()==WL_CONNECTED){ Serial.print("\nWiFi IP: "); Serial.println(WiFi.localIP()); }
  else Serial.println("\nWiFi failed.");
}

// --- New sensor helpers ---
float readProximityCm(){
  pinMode(PROX_TRIG_PIN, OUTPUT);
  pinMode(PROX_ECHO_PIN, INPUT);
  digitalWrite(PROX_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(PROX_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(PROX_TRIG_PIN, LOW);
  unsigned long dur = pulseIn(PROX_ECHO_PIN, HIGH, 20000UL);
  if(dur==0){
    // synthetic oscillation for simulation
    return 14.0f + 6.0f * sin(millis()/3000.0f);
  }
  return (float)dur * 0.0343f / 2.0f;
}

int readMotion(){
  pinMode(PIR_PIN, INPUT);
  int v = digitalRead(PIR_PIN);
  if(v!=HIGH && v!=LOW){
    static unsigned long last=0; static bool state=false;
    if(millis()-last>7000){ last=millis(); state=!state; }
    return state?1:0;
  }
  return v?1:0;
}

String buildPayload(float t,float h,float gasPpm,float gasRaw){
  doc.clear();
  doc["api_key"]=DEVICE_API_KEY;
  JsonArray readings = doc.createNestedArray("readings");
  auto add=[&](const char* type,float v,const char* unit){
    if(isnan(v)) return;
    JsonObject o = readings.createNestedObject();
    o["sensor_type"]=type; o["value"]=v; o["unit"]=unit;
    String ts=isoTimestampUTC(); if(ts.length()) o["recorded_at"]=ts;
  };
  if(!isnan(t) && t>-40 && t<125) add("temp",t,"C");
  if(!isnan(h) && h>=0 && h<=100) add("humi",h,"%");
  if(gasMaxLocked && !isnan(gasPpm)){
    JsonObject g=readings.createNestedObject();
    g["sensor_type"]="gas";
    g["value"]=gasPpm;
    g["unit"]="ppm";
    g["raw"]=gasRaw;
    if(!gasMetaSent){
      g["min"]=gasRawMin;
      g["max"]=gasRawMax;
      g["cal_src"]=usedStoredCalibration?"stored":"fresh";
    }
    String ts=isoTimestampUTC(); if(ts.length()) g["recorded_at"]=ts;
  }
  // New sensors
  float prox = readProximityCm();
  if(!isnan(prox)) add("prox", prox, "cm");
  int motion = readMotion();
  {
    JsonObject m = readings.createNestedObject();
    m["sensor_type"] = "motion";
    m["value"] = motion;
    m["unit"] = "";
    String ts=isoTimestampUTC(); if(ts.length()) m["recorded_at"]=ts;
  }
  // Optional debug to detect payload truncation
  if (doc.overflowed()) {
    Serial.println(F("[WARN] ArduinoJson buffer overflow while building payload; some readings may be missing"));
  }
  String out; serializeJson(doc,out); return out;
}

bool postJSON(const String& payload){
  const char* host = USE_TUNNEL?TUNNEL_HOST:LAN_HOST;
  uint16_t port    = USE_TUNNEL?TUNNEL_PORT:LAN_PORT;
  bool useTLS = USE_TUNNEL;
  String base = String(useTLS?"https://":"http://")+host;
  if(!((useTLS && port==443) || (!useTLS && port==80))) base+=":"+String(port);
  String url = base + INGEST_PATH;
  Serial.println("POST " + url);
  int attempts=0, backoff=600;
  while(attempts<3){
    attempts++; int code=-1;
    if(useTLS){
      WiFiClientSecure c; c.setInsecure();
      HTTPClient h; if(!h.begin(c,url)){ Serial.println("Begin failed"); return false; }
      h.addHeader("Content-Type","application/json");
      h.addHeader("X-Device-Agent","ESP32");
      h.setTimeout(8000);
      code=h.POST(payload);
      if(code>0){
        Serial.printf("Attempt %d => %d\n", attempts, code);
        String body=h.getString();
        if(code>=200 && code<300){ Serial.println("OK: "+body); h.end(); return true; }
        else Serial.println("Err: "+body);
      } else Serial.printf("HTTPS err attempt %d (code=%d)\n", attempts, code);
      h.end();
    } else {
      WiFiClient c; HTTPClient h;
      if(!h.begin(c,url)){ Serial.println("Begin failed"); return false; }
      h.addHeader("Content-Type","application/json");
      h.addHeader("X-Device-Agent","ESP32-LAN");
      h.setTimeout(6000);
      code=h.POST(payload);
      if(code>0){
        Serial.printf("Attempt %d => %d\n", attempts, code);
        String body=h.getString();
        if(code>=200 && code<300){ Serial.println("OK: "+body); h.end(); return true; }
        else Serial.println("Err: "+body);
      } else Serial.printf("HTTP err attempt %d (code=%d)\n", attempts, code);
      h.end();
    }
    delay(backoff); backoff*=2;
  }
  Serial.println("All attempts failed.");
  return false;
}

/* Setup */
void setup(){
  Serial.begin(115200); delay(150); Serial.println();
  Serial.println("=== STEP 9 v2: Calibration + Smoothing ===");
  Serial.println("Send 'R' in first 5s to force recalibration.");
  pinMode(GAS_PIN, INPUT);
  pinMode(PROX_TRIG_PIN, OUTPUT);
  pinMode(PROX_ECHO_PIN, INPUT);
  pinMode(PIR_PIN, INPUT);
  dht.begin();
  for(int i=0;i<3;i++){ dht.readTemperature(); dht.readHumidity(); delay(800); }

  // Serial override window
  unsigned long start=millis(); bool serialForce=false;
  while(millis()-start<5000){
    if(Serial.available()){ char c=Serial.read(); if(c=='R'||c=='r'){ serialForce=true; break; } }
    delay(50);
  }
  if(strcmp(WIFI_SSID,"Wokwi-GUEST")==0 && !USE_TUNNEL){
    Serial.println("[WARN] For Wokwi enabling tunnel"); USE_TUNNEL=true;
  }

  bool loaded = (!FORCE_RECAL && !serialForce) ? loadCalibration() : false;
  connectWiFi(); syncTime();
  if(loaded) Serial.println("[CAL] Using stored calibration.");
  else { Serial.println("[CAL] Fresh calibration baseline phase."); captureGasMin(); }
}

/* Loop */
void loop(){
  handleSerialCommands();
  connectWiFi();
  unsigned long now=millis();

  if(!gasMaxLocked && now - lastGasPoll >= GAS_POLL_MS){
    lastGasPoll=now;
    float r=readGasBlockAvg();
    considerLockMax(r);
  }

  if(now - lastDhtPoll >= DHT_INTERVAL_MS){
    lastDhtPoll=now;
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    // Outlier rejection
    if(!isnan(t)){
      if(isnan(lastGoodTemp) || fabs(t-lastGoodTemp) <= TEMP_SPIKE_MAX_DIFF) { dhtTemp=t; lastGoodTemp=t; }
    }
    if(!isnan(h)){
      if(isnan(lastGoodHumi) || fabs(h-lastGoodHumi) <= HUMI_SPIKE_MAX_DIFF){ dhtHumi=h; lastGoodHumi=h; }
    }
  }

  float raw = readGasBlockAvg();
  float ppmInstant = gasMaxLocked ? mapGasToPPM(raw) : NAN;
  if(gasMaxLocked && !isnan(ppmInstant)){
    if(isnan(gasPpmEma)) gasPpmEma=ppmInstant;
    else gasPpmEma += GAS_PPM_EMA_ALPHA * (ppmInstant - gasPpmEma);
  }
  float ppmSend = gasMaxLocked ? gasPpmEma : NAN;

  bool firstSend = isnan(lastSentTemp) && isnan(lastSentHumi) && isnan(lastSentGasPPM);

  bool tempChanged = (!isnan(dhtTemp) && !isnan(lastSentTemp) && fabs(dhtTemp-lastSentTemp)>=TEMP_DELTA_MIN) ||
                     (firstSend && !isnan(dhtTemp));
  bool humiChanged = (!isnan(dhtHumi) && !isnan(lastSentHumi) && fabs(dhtHumi-lastSentHumi)>=HUMI_DELTA_MIN) ||
                     (firstSend && !isnan(dhtHumi));

  float curRatio = linearRatio(raw);
  float lastRatio = NAN;
  if(gasMaxLocked && !isnan(lastSentGasPPM)){
    float lastLog=log10(lastSentGasPPM);
    float f=(lastLog - log10(PPM_MIN))/(log10(PPM_MAX)-log10(PPM_MIN));
    if(f<0) f=0; if(f>1) f=1;
    lastRatio=f;
  }
  bool gasChangedRatio = (gasMaxLocked && !isnan(curRatio) && !isnan(lastRatio) && fabs(curRatio-lastRatio) >= GAS_RATIO_DELTA_MIN);
  bool gasChangedPpm   = (gasMaxLocked && !isnan(ppmSend) && !isnan(lastSentGasPPM) && fabs(ppmSend-lastSentGasPPM) >= GAS_PPM_DELTA_MIN);
  bool gasChanged = gasChangedRatio || gasChangedPpm || (firstSend && gasMaxLocked && !isnan(ppmSend));

  // Also consider proximity/motion deltas to trigger sends
  float curProx = readProximityCm();
  int   curMotion = readMotion();
  bool proxChanged = (!isnan(curProx) && !isnan(lastSentProx) && fabs(curProx-lastSentProx) >= PROX_DELTA_MIN) ||
                     (isnan(lastSentProx) && !isnan(curProx));
  bool motionChanged = (curMotion != lastSentMotion);

  bool anyChanged = tempChanged || humiChanged || gasChanged || proxChanged || motionChanged;
  bool minGap = (now - lastPost) >= MIN_POST_INTERVAL;
  bool forceDue = (now - lastPost) >= FORCE_INTERVAL;

  if((anyChanged && minGap) || forceDue){
  String payload = buildPayload(dhtTemp, dhtHumi, ppmSend, raw);
    Serial.print("Trigger: ");
    if(forceDue && !anyChanged) Serial.print("heartbeat ");
    if(tempChanged) Serial.print("T ");
    if(humiChanged) Serial.print("H ");
    if(gasChanged) Serial.print("G ");
  if(proxChanged) Serial.print("P ");
  if(motionChanged) Serial.print("M ");
    Serial.println();
    Serial.println("Payload: " + payload);
    if(WiFi.status()==WL_CONNECTED){
      bool ok = postJSON(payload);
      lastPost=now;
      if(ok){
        if(tempChanged && !isnan(dhtTemp)) lastSentTemp=dhtTemp;
        if(humiChanged && !isnan(dhtHumi)) lastSentHumi=dhtHumi;
        if(gasChanged && !isnan(ppmSend)){ lastSentGasPPM=ppmSend; if(!gasMetaSent) gasMetaSent=true; }
    if(!isnan(curProx)) lastSentProx = curProx;
    lastSentMotion = curMotion;
      }
    } else {
      Serial.println("Skip POST: WiFi down");
      lastPost=now;
    }
  }

  if(now - lastJson >= PRINT_INTERVAL_MS){
    lastJson = now;
    String dbg = buildPayload(dhtTemp, dhtHumi, ppmSend, raw);
    static String lastDbg;
    if(dbg != lastDbg){
      Serial.println("[DBG] " + dbg);
      lastDbg = dbg;
    }
  }

  delay(40);
}