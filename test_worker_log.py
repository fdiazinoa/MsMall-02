
import logging
from worker_importacion import insert_load_log
import uuid
import sys

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

def test_log():
    try:
        batch_id = str(uuid.uuid4())
        print(f"Testing with batch_id: {batch_id}")
        
        insert_load_log(
            local_nombre="TEST_LOCAL", 
            archivo="test_file.txt", 
            estado="test", 
            mensaje="Test log insertion from debugger", 
            batch_id=batch_id, 
            detalles=[{"info": "test"}]
        )
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_log()
