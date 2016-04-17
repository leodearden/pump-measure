#!/usr/bin/env python
'''This version of the readserial program demonstrates using python to write
an output file'''

from datetime import datetime
import serial, io, re

outfile='/Users/leo/data/pump-measure.csv'

ser = serial.Serial(
    port='/dev/tty.usbserial',
    baudrate=9600,
)
sio = io.TextIOWrapper(
    io.BufferedRWPair(ser, ser, 1),
    newline='\r'
)
with open(outfile,'a') as f: #appends to existing file
    while ser.isOpen():
        try:
            reading = sio.readline()
        except serial.SerialException as e:
            #There is no new data from serial port
            continue
        except TypeError as e:
            #Disconnect of USB->UART occured
            break
        #\t is tab; \n is line separator
        match = re.search(r'([0-9.]+)g', reading, re.DOTALL)
        if match:
            weight = float(match.group(1))
            f.write(str(weight) + '\n')
            f.flush() #included to force the system to write to disk
        else:
            print "couldn't parse printer message: '{}'".format(reading)
ser.close()