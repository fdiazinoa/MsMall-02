
from worker_importacion import normalize_date
import logging

# Setup basic logging to see output
logging.basicConfig(level=logging.INFO)

def test_dates():
    test_cases = [
        ("18/01/2026", "2026-01-18"),
        ("2026-01-18", "2026-01-18"),
        ("01/18/2026", "2026-01-18"),
        ("18-01-2026", "2026-01-18"),
        ("2026/01/18", "2026-01-18"),
        ("invalid", None),
        ("", None),
        (None, None)
    ]
    
    failures = 0
    for input_date, expected in test_cases:
        result = normalize_date(input_date)
        if result != expected:
            print(f"FAIL: Input '{input_date}' -> Got '{result}', Expected '{expected}'")
            failures += 1
        else:
            print(f"PASS: Input '{input_date}' -> '{result}'")
            
    if failures == 0:
        print("\nAll tests passed!")
    else:
        print(f"\n{failures} tests failed.")
        exit(1)

if __name__ == "__main__":
    test_dates()
