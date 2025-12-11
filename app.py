import streamlit as st
import pandas as pd
import paho.mqtt.client as mqtt
from datetime import datetime

# ==========================================
# KONFIGURASI STREAMLIT
# ==========================================
st.set_page_config(page_title="Dashboard Gudang Kerupuk", layout="wide")
st.title("🌞 Dashboard Monitoring Jemur Kerupuk – IoT MQTT Realtime")

# Simpan data realtime
if "data" not in st.session_state:
    st.session_state.data = []

# ==========================================
# MQTT CALLBACK
# ==========================================
def on_message(client, userdata, msg):
    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        nilai = msg.payload.decode()

        st.session_state.data.append({
            "timestamp": waktu,
            "topic": msg.topic,
            "nilai": nilai
        })
    except:
        pass

# ==========================================
# KONFIGURASI MQTT
# ==========================================
BROKER = "broker.hivemq.com"

TOPIK_LIST = [
    "smuhsa/gudang/suhu",
    "smuhsa/gudang/kelembapan",
    "smuhsa/gudang/ldr",
    "smuhsa/gudang/status",
    "smuhsa/gudang/pintu",
    "smuhsa/gudang/log"
]

client = mqtt.Client()
client.on_message = on_message
client.connect(BROKER, 1883)

for t in TOPIK_LIST:
    client.subscribe(t)

client.loop_start()

st.success(f"MQTT Terhubung: {BROKER}")

# ==========================================
# TAMPILKAN DATA REALTIME
# ==========================================
if len(st.session_state.data) > 0:
    df = pd.DataFrame(st.session_state.data)

    st.subheader("📌 Data Realtime Masuk")
    st.dataframe(df.tail(20), use_container_width=True)

    # PIVOT DATA
    df_pivot = df.pivot_table(
        index="timestamp",
        columns="topic",
        values="nilai",
        aggfunc="last"
    ).reset_index()

    # Konversi numerik yang bisa
    for col in ["smuhsa/gudang/suhu", "smuhsa/gudang/kelembapan", "smuhsa/gudang/ldr"]:
        if col in df_pivot:
            df_pivot[col] = pd.to_numeric(df_pivot[col], errors="coerce")

    # TAMPILKAN GRAFIK
    if "smuhsa/gudang/suhu" in df_pivot:
        st.subheader("🌡 Grafik Suhu")
        st.line_chart(df_pivot["smuhsa/gudang/suhu"])

    if "smuhsa/gudang/kelembapan" in df_pivot:
        st.subheader("💧 Grafik Kelembapan")
        st.line_chart(df_pivot["smuhsa/gudang/kelembapan"])

    if "smuhsa/gudang/ldr" in df_pivot:
        st.subheader("🔆 Grafik Intensitas Cahaya (LDR)")
        st.line_chart(df_pivot["smuhsa/gudang/ldr"])

    # STATUS TERBARU
    if "smuhsa/gudang/status" in df_pivot:
        st.subheader("🌤 Status Cahaya (Realtime)")
        st.info(df_pivot["smuhsa/gudang/status"].iloc[-1])

    if "smuhsa/gudang/pintu" in df_pivot:
        st.subheader("🚪 Status Pintu (Realtime)")
        st.warning(df_pivot["smuhsa/gudang/pintu"].iloc[-1])

else:
    st.info("Menunggu data dari MQTT...")
