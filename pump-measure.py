#!/usr/bin/env python
'''This version of the readserial program demonstrates using python to write
an output file'''

from datetime import datetime
import serial, io, re, numpy, itertools, glob, csv
from printrun.printcore import printcore
from time import sleep

OUTFILE='/Users/leo/data/pump-measure.csv'
MAX_SD_RATIO = 0.1
N_SAMPLES = 3
N_REPEATS = 10
MAX_DURATION = 30
# MAX_DURATION = 10
REVS = [0.1, 0.3, 1, 3, 10, 100, 1000]
FEEDS = [1, 3, 10, 30, 100, 300, 1000, 1800, 3000]
# REVS = [10, 100, 1000]
# FEEDS = [10, 30, 100, 300, 1000, 1800, 3000]
PUMPS = ['X', 'Y']
# PUMPS = ['X']
WAIT_S = 5

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

def read_weight(sio, ser):
    while True:
        try:
            # drain input
            while ser.inWaiting():
                sio.readline()
            reading = sio.readline()
            match = re.search(r'([0-9.]+)g', reading, re.DOTALL)
            if match:
                return float(match.group(1))
            else:
                print "couldn't parse printer message: '{}'".format(reading)
        except serial.SerialException as e:
            #There is no new data from serial port
            print 'trying again to read'
            continue

def read_mean_weight(sio, samples, max_sd_ratio):
    weights = [read_weight(sio) for _ in xrange(samples)]
    wa = numpy.array(weights)
    sd = numpy.std(wa, ddof=1)
    w = numpy.mean(wa)
    if sd/w > max_sd_ratio:
        raise Exception('Excessive deviation in readings. Drift or problem? (readings {}, sd = {}, mean = {})'.format(weights, sd, w)) 
    return w

class Test(object):
    def __init__(self, feed, revs, pump, repeats):
        self.feed = feed
        self.revs = revs
        self.pump = pump
        self.repeats = repeats
        self.result = None

    @property
    def duration(self):
        return 60*self.revs/self.feed

    @property
    def forward(self):
        return 'G0 {}{} F{}'.format(self.pump, self.revs, self.feed)

    @property
    def back(self):
        return 'G0 {}-{} F{}'.format(self.pump, self.revs, self.feed)

    def __str__(self):
        return 'Test {} for {} revs at feed {} in {}s (result = {})'.format(t.pump, t.revs, t.feed, t.duration, t.result)

    __repr__ = __str__

    def run(self, sio, ser):
        self.result = {
            'pump': self.pump,
            'revs': self.revs,
            'feed': self.feed,
        }
        for rep in xrange(self.repeats):
            for command, name, sign in ((t.forward, 'forward', 1), (t.back, 'back', -1)):
#                 before = read_mean_weight(sio, N_SAMPLES, MAX_SD_RATIO)
                before = read_weight(sio, ser)
#                 print 'before = {}, sending "{}"'.format(before, command)
                printer.send(command)
                sleep(t.duration + WAIT_S)
#                 after = read_mean_weight(sio, N_SAMPLES, MAX_SD_RATIO)
                after = read_weight(sio, ser)
#                 print 'after = {}'.format(after)
                delta = after - before
#                 print 'delta = {}'.format(delta)
                self.result['T{}_{}'.format(rep, name)] = delta * sign


tests = filter(lambda t: t.duration <= MAX_DURATION, [Test(f, r, p, N_REPEATS) for f, r, p in itertools.product(REVS, FEEDS, PUMPS)])

ser = serial.Serial(
    port='/dev/tty.usbserial',
    baudrate=9600,
)
sio = io.TextIOWrapper(
    io.BufferedReader(ser, 1),
    newline='\r'
)

assert len(glob.glob('/dev/tty.usbmodem*')) == 1, "Too many usb modems instantiated. Can't tell which one is the Smoothieboard."
printer_interface = glob.glob('/dev/tty.usbmodem*')[0]
print 'printer_interface = {}'.format(printer_interface)
printer = printcore()
printer.connect(port=printer_interface, baud=115200)
sleep(3)
printer.send("G91")

with open(OUTFILE,'w') as f:
    for t in tests:
        t.run(sio, ser)
        print t
    writer = csv.DictWriter(f, sorted(tests[0].result.iterkeys()))
    writer.writeheader()
    writer.writerows([t.result for t in tests])
ser.close()
printer.disconnect()