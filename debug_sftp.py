
import paramiko
import sys
import getpass
import stat
from datetime import datetime

def debug_sftp(host, port, user, password, path):
    print(f"\n--- Conectando a {host}:{port} como {user} ---")
    
    try:
        transport = paramiko.Transport((host, int(port)))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        print("✅ Conexión SFTP establecida con éxito.")
        
        print(f"\n--- Analizando ruta: '{path}' ---")
        
        # Intentar determinar si es archivo o directorio
        try:
            st = sftp.stat(path)
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                print(f"📂 '{path}' es un DIRECTORIO.")
                target_dir = path
            else:
                print(f"📄 '{path}' es un ARCHIVO.")
                target_dir = "."  # Si es archivo, listar el directorio actual o el padre?
                # En main.py usamos posixpath.dirname(ruta)
                import posixpath
                target_dir = posixpath.dirname(path) or "."
                print(f"   -> Listaremos el directorio padre: '{target_dir}'")
        except FileNotFoundError:
             print(f"⚠️ La ruta '{path}' no existe o no se puede acceder directamente (stat failed).")
             print("   -> Intentaremos listar como si fuera un directorio de todos modos.")
             target_dir = path
        except Exception as e:
            print(f"⚠️ Error haciendo stat: {e}")
            target_dir = path

        print(f"\n--- Listando contenidos de '{target_dir}' ---")
        files = sftp.listdir_attr(target_dir)
        
        if not files:
            print("📭 El directorio está vacío.")
        
        print(f"{'PERMISOS':<12} {'TAMAÑO':<10} {'FECHA':<20} {'NOMBRE'}")
        print("-" * 60)
        
        found_json = False
        for attr in files:
            timestamp = datetime.fromtimestamp(attr.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            is_dir = stat.S_ISDIR(attr.st_mode)
            type_icon = "📂" if is_dir else "📄"
            print(f"{str(attr.st_mode):<12} {attr.st_size:<10} {timestamp:<20} {type_icon} {attr.filename}")
            
            if not is_dir and attr.filename.lower().endswith('.json'):
                found_json = True

        print("-" * 60)
        if found_json:
            print("✅ ¡SE ENCONTRARON ARCHIVOS JSON!")
        else:
            print("❌ NO se encontraron archivos .json en este listado.")

        sftp.close()
        transport.close()

    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    host = "sftp.megacentro.com.do"
    port = 22
    
    print("Herramienta de Diagnóstico SFTP para MsMall")
    print(f"Host: {host}")
    
    user = input("Usuario SFTP: ")
    password = getpass.getpass("Contraseña SFTP: ")
    path = input("Ruta remota a analizar (Enter para root '/'): ") or "/"
    
    debug_sftp(host, port, user, password, path)
