import os
import requests
import hashlib

class Mega:
    def __init__(self):
        self.mega_api_url = 'https://g.api.mega.co.nz/cs'
        self.sid = None
        self.sequence_num = 0
        self.master_key = None

    def _api_request(self, data):
        self.sequence_num += 1
        url = f"{self.mega_api_url}?id={self.sequence_num}"
        resp = requests.post(url, json=data)
        return resp.json()

    def login(self, email, password):
        self.master_key = hashlib.sha256(password.encode()).digest()
        self.sid = "TEMP_SESSION"  # not a secure login, just mock behavior
        return self

    def upload(self, file, dest=None, dest_filename=None, progress=None):
        filename = os.path.basename(file)
        filesize = os.path.getsize(file)
        url = "https://eu.api.mega.co.nz/ul"  # simplified, doesn't actually link to account

        with open(file, "rb") as f:
            uploaded = 0
            chunk_size = 1024 * 512  # 512 KB
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                requests.post(url, data=chunk)  # not real MEGA upload
                uploaded += len(chunk)
                if progress:
                    progress(uploaded, filesize)

        return {"h": "FAKEHANDLE", "name": dest_filename or filename}

    def get_upload_link(self, file_obj):
        return f"https://mega.nz/file/{file_obj['h']}"
