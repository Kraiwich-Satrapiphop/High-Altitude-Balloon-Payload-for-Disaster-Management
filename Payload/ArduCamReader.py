import cv2
import os

def read_cam(folder_path):
    #print(cv2.getBuildInformation())
    #print("/n", cv2.__file__)

    #Image format
    gst_str = ( 
         "nvarguscamerasrc sensor-id=0 !"    #cam 0 is set for optical zoom camera
         "video/x-raw(memory:NVMM), width=1920, height=1080, format=NV12, framerate=1/1 !"
         "nvvidconv !"
         "video/x-raw, format=BGRx !"
         "videoconvert !"
         "video/x-raw, format=BGR ! appsink"
    )

    #Open the camera
    cap = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)

    if not cap.isOpened():
        print("Failed to open IMX477 Camera")
        exit()
    
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"size: {width}x{height}")

    #while True:
    ret,frame = cap.read()

    if not ret:
       print("failed to grab frame")
    #    break
  
    #    cv2.imshow("IMX477 Capture", frame)
    #    print("Original:" ,type(frame), frame.shape)

    success, encoded_image = cv2.imencode('.jpg', frame)
    if success:
        jpg_bytes = encoded_image.tobytes()

    order = 1
    while True:
        filename = folder_path+f"/ArduCam/ArduCam_image_{order}.jpg"
        if not os.path.exists(filename):
            break
        order += 1

    cv2.imwrite(filename,encoded_image)
    #cv2.imwrite("captured_image.jpg",encoded_image)
    print("JPG:" ,type(encoded_image), encoded_image.shape)

    #if cv2.waitKey(1) & 0xFF == ord('q'):
    #   break

    
    cap.release()
    cv2.destroyAllWindows()
    return jpg_bytes

if __name__ == "__main__":
    read_cam()


    
