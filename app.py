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

# ===========================================
# CONFIG MQTT & TOPICS (MENYESUAIKAN ESP32)
# ===========================================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 8000

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

# optional model path
MODEL_PATH = "iot_temp_model.pkl"

# timezone Indonesia GMT+7
TZ = timezone(timedelta(hours=7))


# ===========================================
# GLOBAL QUEUE (PENTING)
# ===========================================
GLOBAL_MQ = queue.Queue()


# ===========================================
# UI SETUP
# ===========================================
st.set_page_config(page_title="IoT Gudang — Dashboard", layout="wide")
st.title("📡 IoT Smart Gudang — Realtime Dashboard")


# ===========================================
# INIT SESSION STATE
# ===========================================
if "logs" not in st.session_state:
    st.session_state.logs = []

if "last" not in st.session_state:
    st.session_state.last = {
        "suhu": None,
        "lembap": None,
        "ldr": None,
        "status": None,
        "pintu": None,
        "log": None
    }

if "ml_model" not in st.session_state:
    try:
        st.session_state.ml_model = joblib.load(MODEL_PATH)
        st.success("ML Model Loaded")
    except:
        st.session_state.ml_model = None
        st.info("Model ML tidak ditemukan (opsional).")


# ===========================================
# MQTT CALLBACKS
# ===========================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        GLOBAL_MQ.put({"_type": "status", "connected": True})
        for t in ALL_TOPICS:
            client.subscribe(t)
    else:
        GLOBAL_MQ.put({"_type": "status", "connected": False})


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()

    GLOBAL_MQ.put({
        "_type": "sensor",
        "topic": topic,
        "value": payload,
        "ts": time.time()
    })


# ===========================================
# MQTT WORKER THREAD
# ===========================================
def start_mqtt_thread():
    def worker():
        client = mqtt.Client()
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


# run worker
start_mqtt_thread()


# ===========================================
# HANDLE INCOMING MESSAGES
# ===========================================
def process_queue():
    updated = False
    while not GLOBAL_MQ.empty():
        item = GLOBAL_MQ.get()
        t = item.get("_type")

        if t == "status":
            st.session_state.connected = item["connected"]

        elif t == "sensor":
            topic = item["topic"]
            val = item["value"]

            if topic == TOPIC_SUHU:
                st.session_state.last["suhu"] = float(val)

            elif topic == TOPIC_KELEMBAPAN:
                st.session_state.last["lembap"] = float(val)

            elif topic == TOPIC_LDR:
                st.session_state.last["ldr"] = int(val)

            elif topic == TOPIC_STATUS:
                st.session_state.last["status"] = val

            elif topic == TOPIC_PINTU:
                st.session_state.last["pintu"] = val

            elif topic == TOPIC_LOG:
                st.session_state.last["log"] = val

            # simpan satu row lengkap jika suhu & lembap sudah masuk
            if st.session_state.last["suhu"] is not None:
                row = dict(st.session_state.last)
                row["ts"] = datetime.fromtimestamp(item["ts"], TZ).strftime("%H:%M:%S")
                st.session_state.logs.append(row)

                if len(st.session_state.logs) > 2000:
                    st.session_state.logs = st.session_state.logs[-2000:]

            updated = True

    return updated


# proses awal
process_queue()


# ===========================================
# UI — LEFT PANEL
# ===========================================
left, right = st.columns([1, 2])

with left:
    st.subheader(" Connection")
    status = st.session_state.get("connected", False)
    st.metric("MQTT Connected", "Yes" if status else "No")

    st.markdown("---")

    st.subheader(" Last Data")
    last = st.session_state.last

    st.write(f"**Suhu**: {last['suhu']} °C")
    st.write(f"**Kelembapan**: {last['lembap']} %")
    st.write(f"**LDR**: {last['ldr']}")
    st.write(f"**Status Cahaya**: {last['status']}")
    st.write(f"**Status Pintu**: {last['pintu']}")
    st.write(f"**Log**: {last['log']}")

    st.markdown("---")
    st.subheader(" Manual LED Control")

    col1, col2 = st.columns(2)
    if col1.button("LED_ON"):
        pub = mqtt.Client()
        pub.connect(MQTT_BROKER, MQTT_PORT)
        pub.publish(TOPIC_KONTROL, "LED_ON")
        pub.disconnect()

    if col2.button("LED_OFF"):
        pub = mqtt.Client()
        pub.connect(MQTT_BROKER, MQTT_PORT)
        pub.publish(TOPIC_KONTROL, "LED_OFF")
        pub.disconnect()

    st.markdown("---")
    st.subheader("Download Logs")

    if st.button("Download CSV"):
        if len(st.session_state.logs) > 0:
            df = pd.DataFrame(st.session_state.logs)
            csv = df.to_csv(index=False).encode()
            st.download_button("Klik untuk download", csv, "log_gudang.csv")
        else:
            st.info("Belum ada data")


# ===========================================
# UI — RIGHT PANEL (CHART)
# ===========================================
with right:
    st.subheader(" Live Chart — Suhu & Lembap")

    df = pd.DataFrame(st.session_state.logs[-200:])

    if not df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["ts"], y=df["suhu"], mode="lines+markers", name="Suhu"))
        fig.add_trace(go.Scatter(x=df["ts"], y=df["lembap"], mode="lines+markers", name="Lembap", yaxis="y2"))

        fig.update_layout(
            height=500,
            yaxis=dict(title="Suhu (°C)"),
            yaxis2=dict(title="Kelembapan (%)", overlaying="y", side="right")
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Menunggu data dari ESP32...")

    st.subheader("Recent Logs")
    st.dataframe(df[::-1])

process_queue()
