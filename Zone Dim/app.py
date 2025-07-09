import os
import time
import random
from flask import Flask, request, jsonify, send_from_directory, session
import pandas as pd
import oracledb
import paramiko
from werkzeug.utils import secure_filename
from flask_cors import CORS

# Flask setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB limit
app.secret_key = 'your_secret_key_here'  # change this to a secure random key
CORS(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# SFTP Config


# Oracle DB Configs
db_configs = {

}

# Allowed numbers
ALLOWED_NUMBERS = {
   
}

# SMS Gateway Info (only accessible from 202 server)


# OTP Store
otp_store = {}

def normalize_phone(phone):
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('01'):
        digits = '880' + digits
    elif digits.startswith('880'):
        pass
    return digits

def log_login(phone):
    with open('login_logs.txt', 'a') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {phone} logged in\n")

def send_sms_via_ssh(to, text):
    cmd = (

    )
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(SSH_SMS_HOST, port=SSH_SMS_PORT, username=SSH_SMS_USER, password=SSH_SMS_PASS, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=20)
        out = stdout.read().decode()
        err = stderr.read().decode()
        code = stdout.channel.recv_exit_status()
        ssh.close()
        print("SMS STDOUT:", out)
        print("SMS STDERR:", err)
        return code == 0
    except Exception as e:
        print("SSH SMS Error:", e)
        return False

@app.route('/login-request', methods=['POST'])
def login_request():
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    norm = normalize_phone(phone)
    if norm not in ALLOWED_NUMBERS:
        return jsonify({'error': 'Phone number not authorized'}), 403
    otp = str(random.randint(100000, 999999))
    otp_store[norm] = (otp, time.time() + 300)
    sms_text = f"Your OTP code is: {otp}. It will expire in 5 minutes."
    sms_sent = send_sms_via_ssh(norm, sms_text)
    if not sms_sent:
        return jsonify({'error': 'Failed to send OTP SMS'}), 500
    return jsonify({'status': 'OTP sent'})

@app.route('/login-verify', methods=['POST'])
def login_verify():
    data = request.json
    phone = data.get('phone')
    otp = data.get('otp')
    if not phone or not otp:
        return jsonify({'error': 'Phone and OTP required'}), 400
    norm = normalize_phone(phone)
    if norm not in otp_store:
        return jsonify({'error': 'No OTP requested for this number'}), 400
    stored_otp, expiry = otp_store[norm]
    if time.time() > expiry:
        otp_store.pop(norm, None)
        return jsonify({'error': 'OTP expired'}), 400
    if otp != stored_otp:
        return jsonify({'error': 'Invalid OTP'}), 400
    session['user'] = norm
    otp_store.pop(norm, None)
    log_login(norm)
    return jsonify({'status': 'logged_in'})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({'status': 'logged_out'})


# ------------- Your existing endpoints below --------------

@app.route('/upload', methods=['POST'])
def upload():
    if 'excel' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['excel']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file type'}), 400

    filename = secure_filename(file.filename)
    timestamp = int(time.time())
    saved_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{timestamp}_{filename}")
    file.save(saved_path)

    print(f"[{time.strftime('%H:%M:%S')}] File uploaded: {filename}")

    try:
        xls = pd.ExcelFile(saved_path)
    except Exception as e:
        return jsonify({'error': f'Failed to read Excel: {str(e)}'}), 400

    # Find sheets
    common_sheet = next((s for s in xls.sheet_names if 'common' in s.lower()), None)
    site_sheet = next((s for s in xls.sheet_names if 'site' in s.lower()), None)

    if not common_sheet or not site_sheet:
        return jsonify({'error': 'Required sheets "common cell data" and "site data" not found'}), 400

    try:
        df_common = xls.parse(common_sheet)
        df_site = xls.parse(site_sheet)

        common_csv = os.path.join(app.config['UPLOAD_FOLDER'], 'common_sell.csv')
        site_csv = os.path.join(app.config['UPLOAD_FOLDER'], 'site_data.csv')

        df_common.to_csv(common_csv, index=False, encoding='utf-8')
        df_site.to_csv(site_csv, index=False, encoding='utf-8')

        print(f"[{time.strftime('%H:%M:%S')}] CSV export completed: common_sell.csv, site_data.csv")

    except Exception as e:
        return jsonify({'error': f'Failed to export CSV: {str(e)}'}), 500

    return jsonify({'status': 'success', 'files': ['common_sell.csv', 'site_data.csv']})


@app.route('/sftp-upload', methods=['POST'])
def sftp_upload():
    csv_files = ['common_sell.csv', 'site_data.csv']
    local_paths = []
    logs = []  # 📝 collect logs

    for f in csv_files:
        path = os.path.join(app.config['UPLOAD_FOLDER'], f)
        if not os.path.isfile(path):
            return jsonify({'error': f'{f} not found on server'}), 400
        local_paths.append(path)

    try:
        log = lambda msg: logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

        log("SFTP: connecting...")
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)

        log("Connected to SFTP server")

        remote_files = sftp.listdir(REMOTE_DIR)
        deleted_count = 0
        for f in remote_files:
            sftp.remove(f"{REMOTE_DIR}/{f}")
            deleted_count += 1
        log(f"SFTP: deleted {deleted_count} files")

        for local_path in local_paths:
            filename = os.path.basename(local_path)
            sftp.put(local_path, f"{REMOTE_DIR}/{filename}")
            log(f"SFTP: uploaded {filename}")

        sftp.close()
        transport.close()
        log("SFTP: done")

    except Exception as e:
        logs.append(f"[{time.strftime('%H:%M:%S')}] SFTP Error: {str(e)}")
        return jsonify({'error': f'SFTP upload failed: {str(e)}', 'log': logs}), 500

    return jsonify({'status': 'success', 'uploaded_files': csv_files, 'log': logs})



def get_dsn(cfg):
    return oracledb.makedsn(cfg['host'], cfg['port'], service_name=cfg['sid'])


def get_connection(db_key):
    cfg = db_configs[db_key]
    dsn = get_dsn(cfg)
    return oracledb.connect(user=cfg['user'], password=cfg['password'], dsn=dsn)


@app.route('/run-db202', methods=['POST'])
def run_db202():
    try:
        conn = get_connection('db202')
        cursor = conn.cursor()

        cursor.execute("SELECT MONTH_KEY FROM DATE_DIM WHERE TRUNC(DATE_VALUE,'MM') = TRUNC(SYSDATE,'MM')")
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Month key not found for current month'}), 500
        month_key = row[0]

        cursor.execute("DELETE FROM ZONE_DIM_FULL WHERE MONTH_KEY = :mk", [month_key])
        conn.commit()

        insert_sql = """
        INSERT INTO ZONE_DIM_FULL 
        (SITE_ID, SITE_NAME, LONGITUDE, LATITUDE, CELL_CODE, CGI, LAC, CI, CELL_NAME, FULL_ADDRESS, SHOW_ADDRESS, UPAZILA, DISTRICT, DIVISION, TECHNOLOGY, MSC, COUNTRY, MONTH_KEY)
        SELECT 
            A.SITE_ID, SITE_NAME, LONGITUDE, LATITUDE, CELL_CODE, CGI_ECGI AS CGI, LAC_TAL AS LAC, CI_TAC AS CI, CELL_NAME, FULL_ADDRESS, 
            SHOW_ADDRESS, UPPER(UPAZILA), UPPER(DISTRICT), UPPER(DIVISION), A.TECHNOLOGY, MSC, 'Bangladesh', :mk
        FROM COMMON_SELL_EXT A, SITE_DATA_EXT B
        WHERE A.SITE_ID = B.SITE_ID
        """
        cursor.execute(insert_sql, [month_key])
        inserted_count = cursor.rowcount
        conn.commit()

        cursor.execute("""
        SELECT CGI, COUNT(CGI)
        FROM ZONE_DIM_FULL
        WHERE MONTH_KEY = :mk
        GROUP BY CGI
        HAVING COUNT(CGI) <> 1
        """, [month_key])
        duplicates = cursor.fetchall()
        if duplicates:
            dups_list = [{'CGI': d[0], 'count': d[1]} for d in duplicates]
            duplicates_count = len(duplicates)
        else:
            dups_list = []
            duplicates_count = 0

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'month_key': month_key,
            'duplicates': dups_list,
            'duplicates_count': duplicates_count,
            'records_inserted': inserted_count
        })

    except Exception as e:
        return jsonify({'error': f'DB202 operation failed: {str(e)}'}), 500


@app.route('/run-db203', methods=['POST'])
def run_db203():
    try:
        conn = get_connection('db203')
        cursor = conn.cursor()

        cursor.execute("DROP TABLE ZONE_DIM PURGE")
        cursor.execute("CREATE TABLE ZONE_DIM AS SELECT * FROM ZONE_DIM@DWH05TODWH01")
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'status': 'success', 'message': 'DB203 ZONE_DIM updated'})

    except Exception as e:
        return jsonify({'error': f'DB203 operation failed: {str(e)}'}), 500


@app.route('/run-db204', methods=['POST'])
def run_db204():
    try:
        conn = get_connection('db204')
        cursor = conn.cursor()

        cursor.execute("DROP TABLE ZONE_DIM PURGE")
        cursor.execute("CREATE TABLE ZONE_DIM AS SELECT * FROM ZONE_DIM@DWH03TODWH01")
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'status': 'success', 'message': 'DB204 ZONE_DIM updated'})

    except Exception as e:
        return jsonify({'error': f'DB204 operation failed: {str(e)}'}), 500


@app.route('/')
def index():
    return send_from_directory('public', 'index.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=7000)
