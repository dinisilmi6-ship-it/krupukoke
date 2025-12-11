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
# MQTT CONFIG UNTUK STREAMLIT CLOUD (WEBSOCKET)
# ===========================================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 8000    # HARUS 8000 UNTUK STREAMLIT CLOUD (WEBSOCKET MQTT)

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


# ===========================================
# GLOBAL QUEUE
# ===========================================
GLOBAL_MQ = queue.Queue()


# ===========================================
# STREAMLIT UI SETUP
# ===========================================
st.set_page_config(page_title="IoT Smart Gudang", layout="wide")
st.title("📡 IoT Smart Gudang — Realtime Dashboard")


# ===========================================
# INIT SESSION STATE
# ===========================================
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
        "log": None
    }


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
    payload = msg.payload.decode()

    GLOBAL_MQ.put({
        "_type": "sensor",
        "topic": msg.topic,
        "value": payload,
        "ts": time.time()
    })


# ===========================================
# MQTT WORKER THREAD (WEBSOCKET)
# ===========================================
def start_mqtt_thread():
    def worker():
        client = mqtt.Client(transport="websockets")   # WAJIB UNTUK STREAMLIT CLOUD
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


# ===========================================
# PROSES DATA MASUK
# ===========================================
def process_queue():
    while not GLOBAL_MQ.empty():
        item = GLOBAL_MQ.get()
        t = item["_type"]

        if t == "status":
            st.session_state.connected = item["connected"]

        elif t == "sensor":
            topic = item["topic"]
            value = item["value"]

            if topic == TOPIC_SUHU:
                st.session_state.last["suhu"] = float(value)

            elif topic == TOPIC_KELEMBAPAN:
                st.session_state.last["lembap"] = float(value)

            elif topic == TOPIC_LDR:
                st.session_state.last["ldr"] = int(value)

            elif topic == TOPIC_STATUS:
                st.session_state.last["status"] = value

            elif topic == TOPIC_PINTU:
                st.session_state.last["pintu"] = value

            elif topic == TOPIC_LOG:
                st.session_state.last["log"] = value

            # Simpan log lengkap
            row = dict(st.session_state.last)
            row["ts"] = datetime.fromtimestamp(item["ts"], TZ).strftime("%H:%M:%S")
            st.session_state.logs.append(row)

            if len(st.session_state.logs) > 2000:
                st.session_state.logs = st.session_state.logs[-2000:]


process_queue()


# ===========================================
# UI LEFT PANEL
# ===========================================
left, right = st.columns([1, 2])

with left:
    st.subheader("⚡ Connection")
    st.metric("MQTT Connected", "YES" if st.session_state.connected else "NO")

    st.markdown("---")
    last = st.session_state.last

    st.subheader("📊 Last Data")
    st.write(f"**Suhu**: {last['suhu']} °C")
    st.write(f"**Kelembapan**: {last['lembap']} %")
    st.write(f"**LDR**: {last['ldr']}")
    st.write(f"**Status Cahaya**: {last['status']}")
    st.write(f"**Status Pintu**: {last['pintu']}")
    st.write(f"**Log**: {last['log']}")

    st.markdown("---")
    st.subheader("💡 LED Control")

    col1, col2 = st.columns(2)
    if col1.button("LED ON"):
        pub = mqtt.Client(transport="websockets")
        pub.connect(MQTT_BROKER, MQTT_PORT, 60)
        pub.publish(TOPIC_KONTROL, "LED_ON")
        pub.disconnect()

    if col2.button("LED OFF"):
        pub = mqtt.Client(transport="websockets")
        pub.connect(MQTT_BROKER, MQTT_PORT, 60)
        pub.publish(TOPIC_KONTROL, "LED_OFF")
        pub.disconnect()

    st.markdown("---")
    st.subheader("⬇ Download Logs")

    if st.button("Download CSV"):
        if len(st.session_state.logs) > 0:
            df = pd.DataFrame(st.session_state.logs)
            csv = df.to_csv(index=False).encode()
            st.download_button("Klik untuk download", csv, "log_gudang.csv")
        else:
            st.info("Belum ada data")


# ===========================================
# UI RIGHT PANEL (CHART)
# ===========================================
with right:
    st.subheader("📈 Live Chart")

    df = pd.DataFrame(st.session_state.logs[-200:])

    if not df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["ts"], y=df["suhu"], mode="lines+markers", name="Suhu"))
        fig.add_trace(go.Scatter(x=df["ts"], y=df["lembap"], mode="lines+markers", name="Lembap", yaxis="y2"))

        fig.update_layout(
            height=500,
            yaxis=dict(title="Suhu °C"),
            yaxis2=dict(title="Kelembapan %", overlaying="y", side="right")
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Menunggu data dari ESP32...")

    st.subheader("📝 Recent Logs")
    st.dataframe(df[::-1])


process_queue()
