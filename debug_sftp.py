import paramiko
import time
import socket

host = "sftp.megacentro.com.do"
port = 2022
user = "skechers"
# password is not public, I'll assume it's correct from the user's config
# Since I don't have the password, I can't fully test authentication,
# but I can test the initial handshake.

def test():
    print(f"Testing connection to {host}:{port}...")
    start = time.time()
    try:
        # Step 1: TCP check
        sock = socket.create_connection((host, port), timeout=10)
        print(f"TCP connection successful in {time.time() - start:.2f}s")
        
        # Step 2: SSH Handshake
        transport = paramiko.Transport(sock)
        # transport.start_client() # This might wait for banner
        print(f"Starting SSH client...")
        transport.start_client(timeout=10)
        print(f"SSH Handshake successful in {time.time() - start:.2f}s")
        print(f"Remote version: {transport.remote_version}")
        
        transport.close()
    except Exception as e:
        print(f"Error after {time.time() - start:.2f}s: {e}")

if __name__ == "__main__":
    test()
