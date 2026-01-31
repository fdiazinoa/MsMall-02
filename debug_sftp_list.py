import paramiko
import sys

host = "sftp.megacentro.com.do"
port = 2022
user = "skechers"
password = "HL@)53kdXj"
path = "/web/client/files"

print(f"Connecting to {host}:{port} as {user}...")

try:
    transport = paramiko.Transport((host, port))
    transport.connect(username=user, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)
    print("Connection successful.")

    print(f"Listing {path}...")
    try:
        files = sftp.listdir(path)
        print(f"Found {len(files)} items:")
        for f in files:
            print(f" - {f}")
    except FileNotFoundError:
        print(f"Path {path} not found.")
        print("Listing root / instead:")
        files = sftp.listdir("/")
        for f in files:
            print(f" - {f}")
    except Exception as e:
        print(f"Error listing path: {e}")

    sftp.close()
    transport.close()

except Exception as e:
    print(f"Connection failed: {e}")
