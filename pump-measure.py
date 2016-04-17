#!/usr/bin/env python
'''This version of the readserial program demonstrates using python to write
an output file'''

from datetime import datetime
import serial, io, re, numpy

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

def read_mean_weight(sio, samples, max_sd_ratio):
    weights = [read_weight(sio) for _ in xrange(samples)]
    wa = numpy.array(weights)
    sd = numpy.std(wa, ddof=1)
    w = numpy.mean(wa)
    if sd/w > max_sd_ratio:
        raise Exception('Excessive deviation in readings. Drift or problem? (readings {}, sd = {}, mean = {})'.format(weights, sd, w)) 
    return w

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
        print read_mean_weight(sio, 10, 0.3)
ser.close()