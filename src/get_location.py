# get_location.py
import http.server
import socketserver
import threading
import webbrowser
import json
import os
import time

LOCATION_FILE = "user_location.json"

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <title>Get My Location</title>
</head>
<body>
  <h1>📍 Veuillez autoriser la localisation</h1>
  <script>
    navigator.geolocation.getCurrentPosition(function(pos) {
      const data = {
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy: pos.coords.accuracy
      };
      fetch("/location", {
        method: "POST",
        body: JSON.stringify(data)
      }).then(() => {
        document.body.innerHTML = "<h2>✅ Position enregistrée. Vous pouvez fermer cette page.</h2>";
      });
    }, function(error) {
      document.body.innerHTML = "<h2>❌ Impossible de détecter la position.</h2>";
    });
  </script>
</body>
</html>
"""

class LocationHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len)
        with open(LOCATION_FILE, "w") as f:
            f.write(body.decode("utf-8"))
        self.send_response(200)
        self.end_headers()

def get_location_from_browser():
    PORT = 8899
    handler = LocationHandler

    with socketserver.TCPServer(("localhost", PORT), handler) as httpd:
        def server_thread():
            httpd.serve_forever()

        thread = threading.Thread(target=server_thread)
        thread.daemon = True
        thread.start()

        print("🌐 Open your browser to allow location...")
        webbrowser.open(f"http://localhost:{PORT}")

        # Wait for the file to be written
        for _ in range(30):  # wait max 30 seconds
            if os.path.exists(LOCATION_FILE):
                with open(LOCATION_FILE, "r") as f:
                    data = json.load(f)
                httpd.shutdown()
                os.remove(LOCATION_FILE)
                return data
            time.sleep(1)

        httpd.shutdown()
        print("⏳ Timeout waiting for location.")
        return None

if __name__ == "__main__":
    location = get_location_from_browser()
    if location:
        print("📍 Detected location:")
        print(location)
    else:
        print("❌ Failed to get location.")
