import paramiko
import logging
import sys

# Setup logging
logging.basicConfig()
logging.getLogger("paramiko").setLevel(logging.DEBUG)

host = "sftp.megacentro.com.do"
port = 2022
user = "skechers"
password = "HL@)53kdXj"

print(f"Connecting to {host}:{port}...")

try:
    transport = paramiko.Transport((host, port))
    transport.connect(username=user, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)
    print("Connection successful!")
    print(f"CWD: {sftp.getcwd()}")
    print("Listing files in . :")
    print(sftp.listdir('.'))
    sftp.close()
    transport.close()
except Exception as e:
    print(f"Connection failed: {e}")
    # Keep alive for a bit to ensure logs flush
    import time
    time.sleep(1)
