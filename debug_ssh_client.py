import paramiko
import logging

# Setup logging
logging.basicConfig()
logging.getLogger("paramiko").setLevel(logging.DEBUG)

host = "sftp.megacentro.com.do"
port = 2022
user = "skechers"
password = "HL@)53kdXj"

print(f"Connecting with SSHClient to {host}:{port}...")

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=10, banner_timeout=10, auth_timeout=10)
    
    sftp = client.open_sftp()
    print("SSHClient Connection successful!")
    print("Listing files in . :")
    print(sftp.listdir('.'))
    sftp.close()
    client.close()
except Exception as e:
    print(f"SSHClient Connection failed: {e}")
