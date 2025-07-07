import os
import time
from flask import Flask, request, jsonify, send_from_directory
import pandas as pd
import oracledb
import paramiko
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

# SFTP Config
SFTP_HOST =
SFTP_PORT =
SFTP_USERNAME =
SFTP_PASSWORD =
REMOTE_DIR =

# Oracle DB Configs
db_configs = {

}

def get_dsn(cfg):
    return oracledb.makedsn(cfg['host'], cfg['port'], service_name=cfg['sid'])

def get_connection(db_key):
    cfg = db_configs[db_key]
    dsn = get_dsn(cfg)
    return oracledb.connect(user=cfg['user'], password=cfg['password'], dsn=dsn)

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

    except Exception as e:
        return jsonify({'error': f'Failed to export CSV: {str(e)}'}), 500

    return jsonify({'status': 'success', 'files': ['common_sell.csv', 'site_data.csv']})

@app.route('/sftp-upload', methods=['POST'])
def sftp_upload():
    csv_files = ['common_sell.csv', 'site_data.csv']
    local_paths = []
    for f in csv_files:
        path = os.path.join(app.config['UPLOAD_FOLDER'], f)
        if not os.path.isfile(path):
            return jsonify({'error': f'{f} not found on server'}), 400
        local_paths.append(path)

    try:
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Clear remote dir
        for f in sftp.listdir(REMOTE_DIR):
            sftp.remove(f"{REMOTE_DIR}/{f}")

        # Upload CSVs
        for local_path in local_paths:
            filename = os.path.basename(local_path)
            sftp.put(local_path, f"{REMOTE_DIR}/{filename}")

        sftp.close()
        transport.close()
    except Exception as e:
        return jsonify({'error': f'SFTP upload failed: {str(e)}'}), 500

    return jsonify({'status': 'success', 'uploaded_files': csv_files})

@app.route('/run-db202', methods=['POST'])
def run_db202():
    try:
        conn = get_connection('db202')
        cursor = conn.cursor()

        # Get current month key from DATE_DIM for current month start
        cursor.execute("SELECT MONTH_KEY FROM DATE_DIM WHERE TRUNC(DATE_VALUE,'MM') = TRUNC(SYSDATE,'MM')")
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Month key not found for current month'}), 500
        month_key = row[0]

        # Delete existing rows for this month_key
        cursor.execute("DELETE FROM ZONE_DIM_FULL WHERE MONTH_KEY = :mk", [month_key])
        conn.commit()

        # Insert from CSV loaded tables (assumed loaded as COMMON_SELL_EXT, SITE_DATA_EXT)
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

        # Check duplicates in ZONE_DIM for current month
        cursor.execute("""
        SELECT CGI, COUNT(CGI)
        FROM ZONE_DIM_FULL
        WHERE MONTH_KEY = :mk
        GROUP BY CGI
        HAVING COUNT(CGI) <> 1
        """, [month_key])
        duplicates = cursor.fetchall()
        dups_list = [{'CGI': d[0], 'count': d[1]} for d in duplicates]

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'month_key': month_key,
            'duplicates': dups_list,
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
    app.run(debug=True, host='0.0.0.0', port=5000)
