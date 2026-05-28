import pickle
import socket
import cv2
import numpy as np
import math
import threading
import time
from datetime import datetime

import DataLoggerReader as DLR
import SpaceCamReader as SCR
import ArduCamReader as ACR
import Create_Unique_Folder as CUF
import SystemLogger as SL


#Server Setup
SERVER_PORT = 8081
BUFFER_SIZE = 256

#Set up auto capture time
AUTO_IMAGE_CAP_TIME = 30


def _send_response(conn, data):
    try:
        #print(type(data), data.shape)
        data = pickle.dumps(data)
        conn.sendall(f"{len(data)}".encode('utf-8'))
        if conn.recv(BUFFER_SIZE).decode('utf-8') == 'd':        
            conn.sendall(data)
    except socket.timeout:
        pass
    except ConnectionResetError:
        logger.log("[ThermieServer] Warn: Connection reset error")
    except UnicodeDecodeError:
        logger.log("[ThermieServer] Warn: UnicodeDecode error")
    except pickle.PickleError as e:
        logger.log(f"[ThermieServer] Pickle error: {e}")

def _received_response(conn,addr):
    last_address = addr[0]
    data = conn.recv(BUFFER_SIZE)
    if not data:
        return None
    data = pickle.loads(data)
    data = data.strip()
    return data
    
def auto_capture(folder_path, logger):
    while True:
        try:
            image = SCR.read_cam(folder_path, logger)
            logger.log("[Server] Auto image captured")
        except Exception as e:
            logger.log(f"[Server] Auto capture error: {e}")
        
        time.sleep(AUTO_IMAGE_CAP_TIME)

def main():
    #Create The Images Folder
    folder_path = CUF.folder("Image Folder")
    
    logger = SL.SystemLogger(folder_path, "air_log.txt")
    logger.log("[Server] Air unit system started")
    
    CUF.folder(folder_path+"/SpaceCam")
    CUF.folder(folder_path+"/ArduCam")
    logger.log(f"[Server] Folders Created: '{folder_path}'")
    
    logger.log("[Server] Starting Socket")
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    #Create a socket for TCP
    soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    soc.bind(("0.0.0.0", SERVER_PORT))    #listen to all available network at SERVER_PORT
    soc.listen(1)    #Allow the maximum queued connections
    soc.settimeout(20)    #Set the timeout in seconds
    
    conn = None
    timeout = False
    run_main = True
    logger.log("[Server] Ready")
    
    #Start threading
    threading.Thread(target=auto_capture, args=(folder_path, logger), daemon=True).start()

    while run_main:
        try:
            logger.log("[Server] Waiting...")
            conn, addr = soc.accept()    #Block until the client ask to connect
            logger.log("[Server] Client connected")
            while True:
                data = _received_response(conn,addr)
                if not data:
                    break
                logger.log(f"[Server] Received '{data}'")
                start_time = time.time()
                if data == "test":
                    payload = "This is a testing command"
                    _send_response(conn, payload)
                    end_time = time.time()
                    transmission_time = end_time - start_time
                    logger.log(f"[Server] Test sent — length={len(payload)}B  transmission={transmission_time:.4f}s")
                elif data == "data":
                    Header, Data_RAW, DATA_PARSED = DLR.read_strato4(logger)
                    if not DATA_PARSED:
                        logger.log("[Server] WARN: Data empty — nothing sent to client")
                        break
                    _send_response(conn, DATA_PARSED)
                    end_time = time.time()
                    transmission_time = end_time - start_time
                    logger.log(f"[Server] DATA sent — length={len(DATA_PARSED)}B  transmission={transmission_time:.4f}s")
                elif data == "cam1":
                    try:
                        image = SCR.read_cam(folder_path, logger)
                    except Exception as e:
                        logger.log(f"[Server] WARN: Camera failed — nothing sent to client ({e})")
                        break
                    _send_response(conn, image)
                    end_time = time.time()
                    transmission_time = end_time - start_time
                    logger.log(f"[Server] Image sent — length={len(image)}B  transmission={transmission_time:.4f}s")
                # elif data == "cam2":
                    # image = ACR.read_cam(folder_path)
                    # _send_response(conn, image)
                else:
                    logger.log(f"[Server] WARN: Unknown command '{data}'")
        except KeyboardInterrupt:
            run_main = False
        except socket.timeout:
            timeout = True
        except ConnectionResetError:
            logger.log("[Server] WARN: Connection reset error")
        except UnicodeDecodeError:
            logger.log("[Server] WARN: UnicodeDecode error")
        except pickle.PickleError as e:
            logger.log(f"[Server] ERROR: Pickle error '{e}'")
        except Exception as e:
            logger.log(f"[Server] ERROR: {type(e).__name__}: {e}")
        finally:
            if timeout:
                timeout = False
            elif conn is not None:
                conn.close()
                logger.log("[Server] Connection closed")
                conn = None
    logger.log("[Server] End")
    soc.close()



if __name__ == "__main__":
    main()
