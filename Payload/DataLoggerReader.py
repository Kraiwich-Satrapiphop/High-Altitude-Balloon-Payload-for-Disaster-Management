import serial	#import UART Protocol
import json5	#Import JSON5 format
import time

#Adjust this to your actual serial port

SERIAL_PORT = '/dev/ttyUSB0'	#always ttyUSB0 as we're using 1 UART
BUAD_RATE = 115200

#Commands to request header and data

CMD_HEADER = "{to:'Log',from:'Mst',reci:'headerValsCsv',dir:'g',rc:''}\n"
CMD_DATA = "{to:'Log',from:'Mst',reci:'dataValsCsv',dir: 'g',rc:''}\n"

MAX_RETRIES    = 3
RETRY_DELAY    = 0.5   # seconds between retries
POWERCYCLE_AFTER = 3   # consecutive full-read failures before power cycling
POWERCYCLE_HOLD  = 2   # seconds DTR is asserted (reset pulse)
POWERCYCLE_BOOT  = 5   # seconds to wait for device to boot after cycle

_consec_failures = 0   # module-level consecutive failure counter


def _power_cycle(logger):
    """Reset the datalogger by toggling the DTR line, then wait for boot."""
    logger.log("[Sensors] Power cycling datalogger (DTR toggle)...")
    try:
        with serial.Serial(SERIAL_PORT, BUAD_RATE, timeout=2) as ser:
            ser.dtr = True
            time.sleep(POWERCYCLE_HOLD)
            ser.dtr = False
        logger.log(f"[Sensors] DTR released — waiting {POWERCYCLE_BOOT}s for boot")
        time.sleep(POWERCYCLE_BOOT)
    except Exception as e:
        logger.log(f"[Sensors] Power cycle error: {e}")


def read_strato4(logger):
    global _consec_failures
    header_response = ""
    data_response   = ""
    data_parsed     = None

    try:
        with serial.Serial(SERIAL_PORT, BUAD_RATE, timeout=2) as ser:

            # ── Request header (with retry) ───────────────────────────────────
            for attempt in range(1, MAX_RETRIES + 1):
                ser.reset_input_buffer()
                ser.write(CMD_HEADER.encode())
                header_response = ser.readline().decode().strip()
                if header_response:
                    break
                logger.log(f"[Sensors] No header response (attempt {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

            if not header_response:
                logger.log("[Sensors] Header failed after all retries")
                return header_response, data_response, data_parsed

            # ── Request data (with retry) ─────────────────────────────────────
            for attempt in range(1, MAX_RETRIES + 1):
                ser.reset_input_buffer()
                ser.write(CMD_DATA.encode())
                data_response = ser.readline().decode().strip()
                if data_response:
                    break
                logger.log(f"[Sensors] No data response (attempt {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

            if not data_response:
                logger.log("[Sensors] Data failed after all retries")
                return header_response, data_response, data_parsed

            # ── Parse JSON5 ───────────────────────────────────────────────────
            try:
                parsed = json5.loads(data_response)
                data_parsed = parsed.get('pl', {}).get('valsCsv')
                if data_parsed:
                    logger.log("[Sensors] Successfully read the sensors")
                    _consec_failures = 0
                else:
                    logger.log("[Sensors] Sensors data missing or empty")
            except json5.JSON5DecodeError as e:
                logger.log(f"[Sensors] JSON5 parsing failed: '{e}'")
            except Exception as e:
                logger.log(f"[Sensors] Failed to parse JSON5: '{e}'")

    except serial.SerialException as e:
        logger.log(f"[Sensors] Communication error: '{e}'")
    except Exception as e:
        logger.log(f"[Sensors] Error: '{e}'")

    if not data_parsed:
        _consec_failures += 1
        logger.log(f"[Sensors] Consecutive failures: {_consec_failures}/{POWERCYCLE_AFTER}")
        if _consec_failures >= POWERCYCLE_AFTER:
            _consec_failures = 0
            _power_cycle(logger)

    return header_response, data_response, data_parsed

if __name__ == "__main__":
	Header, Data_RAW, DATA_PARSED = read_strato4()
	new_data = Selecting_Data(DATA_PARSED)
	print("\nnew_data: ", new_data)




