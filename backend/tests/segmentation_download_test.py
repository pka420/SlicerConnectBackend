import requests

token=''

url = "http://localhost:8000/segmentations/22/download"
headers = {"Authorization": f"Bearer {token}"}

response = requests.get(url, headers=headers, stream=True)

content_disposition = response.headers.get('Content-Disposition')
if content_disposition:
    filename = content_disposition.split('filename=')[1].strip()
else:
    filename = "downloaded_file.nrrd"

with open(filename, "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)

print(f"Downloaded: {filename}")
