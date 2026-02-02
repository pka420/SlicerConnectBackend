import requests

data={
    "email": "",
    "password": ""
}

response = requests.post(
    'http://localhost:8000/auth/login',
    json=data,
)

token = response.json()['access_token']
#token=''
print(token)

# files = {
#     'file': ('manual_label.nii', open('/home/lucifer/work/faisal-work/manual_label.RIDER_LUNG_orig.nii', 'rb'), 'application/octet-stream')
# }
#
# data = {
#     'project_id': 1,
#     'name': 'lung',
#     'color': '#FF0000'
# }
#
# response = requests.post(
#     'http://localhost:8000/segmentations',
#     files=files,
#     data=data,
#     headers={'Authorization': f'Bearer {token}'}
# )
#
# print(response.json())
