import pickle
import socket
from threading import Thread
import atexit
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os
import csv
from datetime import datetime
import time


import MapPlot as MP
import Create_Unique_Folder as CUF
import SystemLogger as SL
BUFFER_SIZE = 256   #receive massage size
IP = "192.168.144.157"
#"192.168.144.157"  -   Server IP
#"127.0.0.1"    -   Local IP

#Create The Images Folder & csv file
folder_path = CUF.folder("Image Folder")
logger = SL.SystemLogger(folder_path, "ground_log.txt")

def _send(ip_address, cmd_name):
        soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    #Create a TCP socket
        soc.settimeout(20)    #Timeout in seconds
        try:
            soc.connect((ip_address, 8081))    #Connect to the Server
            cmd_string = pickle.dumps(cmd_name)    #serializes the data
            soc.sendall(cmd_string)    #send all the data
            logger.log(f"[Server] Successfully sent: '{cmd_name}'")
            return soc
        except Exception:
            soc.close()
            raise

def _receive(ip_address, soc):
        try:
            data = None
            # chunked data receive
            rec_length = int(soc.recv(BUFFER_SIZE).decode('utf-8'))
            logger.log(f"[Server] Receiving: '{rec_length}'")
            rec_data = b''
            soc.sendall("d".encode('utf-8'))
            while len(rec_data) < rec_length:
                rec_data += soc.recv(BUFFER_SIZE)
            if not rec_data:
                logger.log("[Server] Error: no response received")
            else:
                data = pickle.loads(rec_data)
                logger.log(f"[Server] Successfully received the data")
        except (socket.timeout, socket.gaierror, ConnectionError) as e:
            logger.log(f"[SystemControlWifi] Error: socket error ({e})")
        except (pickle.PickleError, UnicodeDecodeError, ValueError) as e:
            logger.log(f"[SystemControlWifi] Error: data decode error ({e})")
        finally:
            soc.close()
            logger.log("[Server] Socket Closed")
        return data
    
def Create_CSV_File(folder_path):
    Header = [
    [],
    ["Recoreded Data from the Datalogger"],
    [],
    ["Uptime", "Timestamp", "UTC date time", "Fix type", "Latitude (degrees)", "Longtitude (degrees)",
    "Positional dilution of precision", "Altitude (m) above Mean Sea Level", "Ground speed (km/h)",
    "Satellites in view", "Altitude (m) above elipsoid", "Temperature Board", "Temperature Ext LM75", "Temperature Ext MS8607",
    "Pressure Ext (hPa) MS8607", "Humidity (%) MS8607", 
    "Light Intensity Clear (lx)", "Light Intensity Red (lx)", "Light Intensity Green (lx)", "Light Intensity Blue (lx)",
    "Light Intensity Infrared (lx)","Light Intensity UVA",
    "Supply Voltage (V)", "3.3 V board voltage","5 V board voltage", "Vin1 voltage", "Vin2 voltage", "Vin3 voltage",
    "In 1 State", "In 1 Timestamp (s)", "In 2 State", "In 2 Timestamp (s)",
    "Out 1 State", "Out 1 Timestamp (s)", "Out 2 State", "Out 2 Timestamp (s)"]
    ]

    with open(folder_path+"/Data.csv", mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(Header)

def main():
    #Setup
    logger.log("Ground station started")

    CUF.folder(folder_path+"/SpaceCam")
    CUF.folder(folder_path+"/ArduCam")
    Create_CSV_File(folder_path)
    logger.log(f"[Server] Folders & CSV created: '{folder_path}'")

    #main
    while True:
        print("\nEnter Your Command (test/data/cam1/cam2/map): ")
        cmd = input()
        try:
            if cmd == "test":
                #Testing
                start_time = time.time()
                soc = _send(IP, cmd)
                res = _receive(IP, soc)
                end_time = time.time()
                transmission_time = end_time - start_time
                logger.log(f"[Server] Transmission time: {transmission_time:.4f} sec")
            elif cmd == "data":
                #Read Data
                start_time = time.time()
                soc = _send(IP, cmd)
                res = _receive(IP, soc)
                end_time = time.time()
                transmission_time = end_time - start_time
                logger.log(f"[Server] Transmission time: {transmission_time:.4f} sec")

                data = res.split(";")
                with open(folder_path+"/Data.csv", mode="a", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(data)
                MP.Map_Save(data[4], data[5], folder_path, logger)
            elif cmd == "cam1":
                #Read Image
                start_time = time.time()
                soc = _send(IP, cmd)
                res = _receive(IP, soc)
                end_time = time.time()
                transmission_time = end_time - start_time
                logger.log(f"[Server] Transmission time: {transmission_time:.4f} sec")

                nparr = np.frombuffer(res, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = folder_path+f"/SpaceCam/SpaceCam_{timestamp}.jpg"
                cv2.imwrite(filename,image)
            elif cmd == "cam2":
                start_time = time.time()
                soc = _send(IP, cmd)
                res = _receive(IP, soc)
                end_time = time.time()
                transmission_time = end_time - start_time
                logger.log(f"[Server] Transmission time: {transmission_time:.4f} sec")

                nparr = np.frombuffer(res, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = folder_path+f"/SpaceCam/SpaceCam_{timestamp}.jpg"
                cv2.imwrite(filename,image)
            elif cmd == "map":
                MP.Open_Map(folder_path, logger)
            else:
                logger.log(f"[Server] Unknown Input Command: '{cmd}'")
        except Exception as e:
            print(f"Error: {e}")
            logger.log(f"[Server] Command '{cmd}' failed: {e}")
    

if __name__ == "__main__":
    main()






















        
