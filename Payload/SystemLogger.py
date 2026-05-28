import os
from datetime import datetime

class SystemLogger:
    def __init__(self, folder_path, name="log.txt"):
        self.file_path = os.path.join(folder_path, name)

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"

        print(line)

        with open(self.file_path, "a") as f:
            f.write(line + "\n")