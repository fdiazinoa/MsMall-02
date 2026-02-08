
from debug_sftp import debug_sftp

host = "sftp.megacentro.com.do"
port = 2022
user = "cafe-sd-pe"
password = "p48KbH6axZ"
path = "." 

print(f"Running automated diagnostic for {user}@{host}:{port} on path '{path}'")
debug_sftp(host, port, user, password, path)
