from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import pymysql
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
# --- 1. Konfigurasi Aplikasi dan Koneksi ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*") # Izinkan koneksi dari semua domain untuk kemudahan testing

# --- Konfigurasi MySQL ---
# GANTI DENGAN KREDENSIAL DAN NAMA DATABASE ANDA
MYSQL_HOST = os.environ.get('MYSQL_HOST')
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DB = os.environ.get('MYSQL_DB')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT'))
CA_CERT_PATH = os.environ.get('CA_CERT_PATH', 'ca.pem')

def get_db_connection():
    """Membuat dan mengembalikan objek koneksi PyMySQL."""
    return pymysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        port=MYSQL_PORT,
        cursorclass=pymysql.cursors.DictCursor, # Mengembalikan data sebagai dictionary
        ssl={'ca': CA_CERT_PATH}
    )
    
@app.route('/')
def home():
    # Ini hanya untuk menghindari 'Not Found' di browser
    return jsonify({"status": "Server running", "message": "Access API at /api/data/..."})

# --- 2. Endpoint untuk Menerima Data dari IoT ---
@app.route('/api/data/suhu', methods=['POST'])
def receive_iot_data():
    
    # Memastikan request body adalah JSON
    if not request.is_json:
        return jsonify({"message": "Permintaan harus dalam format JSON"}), 400

    data = request.get_json()
    
    # Validasi data yang diterima
    if 'suhu' not in data:
        return jsonify({"message": "Data 'suhu' tidak ditemukan"}), 400

    suhu_value = data['suhu']
    current_time = datetime.now()
    
    # ----------------------------------------------------
    # JALUR A: REAL-TIME KE WEBSITE (Via Socket.IO)
    # ----------------------------------------------------
    # Data dikirim ke semua klien web yang terhubung
    data_to_send = {
        'suhu': suhu_value,
        # ❗ PERUBAHAN 1: Kirim string waktu H:M:S mentah untuk menghindari Timezone shift di browser ❗
        'timestamp': current_time.isoformat() 
    }
    
    # Kirim event 'suhu_update' ke semua klien web
    socketio.emit('suhu_update', data_to_send)
    print(f"[SocketIO] Data suhu {suhu_value} dikirim ke klien.")

    # ----------------------------------------------------
    # JALUR B: PENYIMPANAN DATA KE MYSQL (Historis)
    # ----------------------------------------------------
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Tetap simpan waktu penuh ke database
            sql = "INSERT INTO suhu_log (suhu, timestamp) VALUES (%s, %s)"
            cursor.execute(sql, (suhu_value, current_time))
        conn.commit()
        conn.close()
        print(f"[MySQL] Data suhu {suhu_value} berhasil disimpan.")
        
    except Exception as e:
        print(f"[ERROR DB] Gagal menyimpan data: {e}")
        # Tetap berikan respons berhasil agar IoT tidak mencoba mengirim ulang
    
    return jsonify({"message": "Data diterima dan diproses"}), 200

# --- 3. Endpoint untuk Mengambil Data Historis (Saat Website Dimuat) ---
@app.route('/api/data/historis', methods=['GET'])
def get_historical_data():
    
    data_historis_formatted = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Ambil 50 data terbaru
            sql = "SELECT suhu, timestamp FROM suhu_log ORDER BY timestamp DESC LIMIT 50"
            cursor.execute(sql)
            data_historis = cursor.fetchall()
            
        conn.close()
        
        # ❗ PERUBAHAN 2 (REVISI): Format ulang data historis. Kirim string ISO yang LENGKAP agar JavaScript dapat menguraikannya. ❗
        # PERBAIKI JALUR B: Pengambilan Data Historis
        for item in data_historis:
            if isinstance(item['timestamp'], datetime):
                formatted_time = item['timestamp'].isoformat()
            elif item['timestamp'] is None:
                # ✅ Jika waktu NULL, kirim string kosong (atau lewati item ini)
                formatted_time = "" 
            else:
                # Pertahankan konversi untuk berjaga-jaga (jika bukan datetime/null)
                formatted_time = str(item['timestamp'])
            
            data_historis_formatted.append({
                'suhu': item['suhu'],
                'timestamp': formatted_time
            })
        
    except Exception as e:
        print(f"[ERROR DB] Gagal mengambil data historis: {e}")
        return jsonify([]), 500

    # Mengembalikan data historis yang sudah diformat
    return jsonify(data_historis_formatted), 200

# --- 4. Menjalankan Server ---
if __name__ == '__main__':
    # Pastikan host='0.0.0.0' agar ESP8266 dapat terhubung
    print("Server Flask dan SocketIO sudah berjalan")
    socketio.run(app, host='0.0.0.0', debug=True)    