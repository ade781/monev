from http.server import BaseHTTPRequestHandler
import json
import sys
import os

# Tambahkan direktori root agar bisa import monev_bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import monev_bot

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            monev_bot.main()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "success",
                "message": "Monev Bot dijalankan dengan sukses!"
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "error",
                "message": str(e)
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
