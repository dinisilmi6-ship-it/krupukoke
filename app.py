import streamlit as st
import pandas as pd
import numpy as np
import joblib
import time
import queue
import json
import threading
from datetime import datetime, timezone, timedelta
import plotly.graph_objs as go
import paho.mqtt.client as mqtt

# ---------------------------
# CONFIG MQTT
# ---------------------------
MQTT_BROKER = "broker.emqx.io"   # EMQX gratis WebSocket broker
MQTT_PORT = 8083                 # WebSocket port
TOPIC_SUHU       = "smuhsa/gudang/suhu"
TOPIC_KELEMBAPAN = "smuhsa/gudang/kelembapan"
TOPIC_LDR        = "smuhsa/gudang/ldr"
TOPIC_STATUS     = "smuhsa/gudang/status"
TOPIC_PINTU      = "smuhsa/gudang/pintu"
TOPIC_LOG        = "smuhsa/gudang/log"
TOPIC_KONTROL    = "smuhsa/gudang/kontrol"

ALL_TOPICS = [
    TOPIC_SUHU, TOPIC_KELEMBAPAN, TOPIC_LDR,
    TOPIC_STATUS, TOPIC_PINTU, TOPIC_LOG
]

MODEL_PATH = "iot_temp_model.pkl"
TZ = timezone(timedelta(hours=7))

# ---------------------------
# GLOBAL QUEUE
# ---------------------------
GLOBAL_MQ = queue.Queue()

# ---------------------------
# STREAMLIT UI
# ---------------------------
st.set_page_config(page_title="IoT Smart Gudang", layout="wide")
st.title(" IoT Smart Gudang — Realtime Dashboard")

# ---------------------------
# INIT SESSION STATE
# ---------------------------
if "connected" not in st.session_state:
    st.session_state.connected = False

if "logs" not in st.session_state:
    st.session_state.logs = []

if "last" not in st.session_state:
    st.session_state.last = {
        "suhu": None,
        "lembap": None,
        "ldr": None,
        "status": None,
        "pintu": None,
        "log": None,
        "pred": None,
        "conf": None,
        "anomaly": None
    }

if "ml_model" not in st.session_state:
    st.session_state.ml_model = None

# ---------------------------
# LOAD ML MODEL (optional)
# ---------------------------
@st.cache_resource
def load_ml_model(path):
    try:
        return joblib.load(path)
    except Exception as e:
        st.warning(f"ML model not loaded: {e}")
        return None

st.session_state.ml_model = load_ml_model(MODEL_PATH)

def model_predict_label_and_conf(temp, hum):
    model = st.session_state.ml_model
    if model is None:
        return ("N/A", None)
    X = [[float(temp), float(hum)]]
    try:
        label = model.predict(X)[0]
    except Exception:
        label = "ERR"
    prob = None
    if hasattr(model, "predict_proba"):
        try:
            prob = float(np.max(model.predict_proba(X)))
        except Exception:
            prob = None
    return label, prob

# ---------------------------
# MQTT CALLBACKS
# ---------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        GLOBAL_MQ.put({"_type": "status", "connected": True})
        for t in ALL_TOPICS:
            client.subscribe(t)
    else:
        GLOBAL_MQ.put({"_type": "status", "connected": False})

def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    GLOBAL_MQ.put({
        "_type": "sensor",
        "topic": msg.topic,
        "value": payload,
        "ts": time.time()
    })

# ---------------------------
# MQTT WORKER THREAD (WebSocket)
# ---------------------------
def start_mqtt_thread():
    def worker():
        client = mqtt.Client(transport="websockets")
        client.on_connect = on_connect
        client.on_message = on_message
        while True:
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, 60)
                client.loop_forever()
            except Exception as e:
                GLOBAL_MQ.put({"_type": "error", "msg": str(e)})
                time.sleep(2)
    threading.Thread(target=worker, daemon=True).start()

start_mqtt_thread()

# ---------------------------
# PROCESS INCOMING QUEUE
# ---------------------------
def process_queue():
    while not GLOBAL_MQ.empty():
        item = GLOBAL_MQ.get()
        t = item["_type"]

        if t == "status":
            st.session_state.connected = item["connected"]

        elif t == "sensor":
            topic = item["topic"]
            value = item["value"]

            # update last data
            last = st.session_state.last

            if topic == TOPIC_SUHU:
                last["suhu]()
