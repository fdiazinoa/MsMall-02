import requests

url = "http://localhost:8000/api/v1/mapping/analyze"

# Create a sample CSV in memory
# invoice,date,amount
# 12345,2024-01-29,150.00
content = "invoice,date,amount\n12345,2024-01-29,150.00"

files = {'file': ('sample.csv', content)}
response = requests.post(url, files=files)

print(f"Status: {response.status_code}")
print(response.json())
