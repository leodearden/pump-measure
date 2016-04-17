#!/usr/bin/env python
'''This version of the readserial program demonstrates using python to write
an output file'''

from datetime import datetime
import serial, io, re

# parse input flags for data directory and test space parameters
# build test space tuple list
# connect to pumps
# for each test tuple
#   capture windowed mean weight
#   calculate expected duration
#   send command
#   wait for completion
#   capture windowed mean weight
#   record weight difference

def read_weight(sio):
    while True:
        try:
            reading = sio.readline()
            match = re.search(r'([0-9.]+)g', reading, re.DOTALL)
            if match:
                return float(match.group(1))
            else:
                print "couldn't parse printer message: '{}'".format(reading)
        except serial.SerialException as e:
            #There is no new data from serial port
            continue
    

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
        weight = read_weight(sio)
        if weight:
            f.write(str(weight) + '\n')
            f.flush() #included to force the system to write to disk
ser.close()