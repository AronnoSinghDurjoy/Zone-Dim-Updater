Zone-Dim-Updater
Zone Dim Updater is a lightweight web-based tool designed to streamline the workflow of telecom data engineers. It allows users to upload Excel files, extract specific sheets, convert them into CSV format, securely transfer them to a remote server via SFTP, and trigger Oracle database operations on multiple environments.

🚀 Features
✅ Drag-and-drop Excel file upload

✅ Automatic detection of required sheets (Common Cell Data, Site Data)

✅ CSV generation from Excel sheets

✅ Secure file transfer to remote server using SFTP

✅ Oracle DB operations across three environments (202, 203, 204)

✅ Duplicate detection and summary report

✅ Real-time status logs on the web UI

🖥 Tech Stack
Frontend: HTML, CSS, JavaScript (Vanilla)

Backend: Python (Flask)

Database: Oracle DB (via oracledb)

File Transfer: Paramiko (SFTP)

Excel Handling: Pandas, openpyxl

📁 Folder Structure
Zone-Dim-Updater/
├── uploads/              # Uploaded and generated CSV files
├── public/               # Frontend HTML/JS/CSS files
│   └── index.html
├── app.py                # Main Flask application
├── README.md             # Project documentation
⚙️ Setup Instructions
Clone the repository:

bash
git clone https://github.com/yourusername/Zone-Dim-Updater.git
cd Zone-Dim-Updater
Create and activate virtual environment:

bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
Install dependencies:

bash

pip install -r requirements.txt
Update configuration:

Inside app.py, update:

Oracle DB credentials

SFTP credentials

Remote directory path

Run the application:

bash
python app.py
Access via browser:

arduino
http://localhost:5000
✅ Example Workflow
Drag and drop an Excel file with Common Cell Data and Site Data sheets.

Click Export CSV to generate CSVs.

Click SFTP Upload to transfer files to the remote server.

Run DB operations by selecting DB202, DB203, or DB204.

View logs and status messages live.

📌 Notes
Excel file must contain at least two sheets: Common Cell Data and Site Data.

CSVs are stored in uploads/ before being transferred.

Oracle procedures assume external tables COMMON_SELL_EXT and SITE_DATA_EXT are pre-configured.

🧑‍💻 Author
Aronno Singh – @aronno
Feel free to fork, contribute or suggest improvements!

📄 License
This project is licensed under the MIT License. See LICENSE for more details.

