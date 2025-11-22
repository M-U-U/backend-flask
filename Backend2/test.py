from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import pymysql
from datetime import datetime
import json

# --- 1. Konfigurasi Aplikasi dan Koneksi ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*") # Izinkan koneksi dari semua domain untuk kemudahan testing

# --- Konfigurasi MySQL ---
# GANTI DENGAN KREDENSIAL DAN NAMA DATABASE ANDA
MYSQL_HOST = 'iot-suhu-iot-c570.b.aivencloud.com'
MYSQL_USER = 'avnadmin'
MYSQL_PASSWORD = 'AVNS_oq8ZsY-JXbxT9ii_lNT'
MYSQL_DB = 'defaultdb' 

def get_db_connection():
    """Membuat dan mengembalikan objek koneksi PyMySQL."""
    return pymysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor # Mengembalikan data sebagai dictionary
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
        'timestamp': current_time.strftime('%H:%M:%S') 
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
        for item in data_historis:
            # Pastikan item['timestamp'] adalah objek datetime dari MySQL
            if isinstance(item['timestamp'], datetime):
                # Format ke string ISO 8601 (contoh: 2025-11-22T20:30:00)
                # Ini akan memastikan TANGGAL dan WAKTU dikirim.
                formatted_time = item['timestamp'].isoformat()
            else:
                formatted_time = str(item['timestamp'])

            data_historis_formatted.append({
                'suhu': item['suhu'],
                'timestamp': formatted_time # Kirim waktu yang sudah diformat (ISO String)
            })
        
    except Exception as e:
        print(f"[ERROR DB] Gagal mengambil data historis: {e}")
        return jsonify([]), 500

    # Mengembalikan data historis yang sudah diformat
    return jsonify(data_historis_formatted), 200

# --- 4. Menjalankan Server ---
if __name__ == '__main__':
    # Pastikan host='0.0.0.0' agar ESP8266 dapat terhubung
    print("Server Flask dan SocketIO berjalan di http://0.0.0.0:5000")

    socketio.run(app, host='0.0.0.0', port=5000, debug=True)    
