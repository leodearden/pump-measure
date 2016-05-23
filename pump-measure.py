#!/usr/bin/env python
'''This version of the readserial program demonstrates using python to write
an output file'''

from datetime import datetime
import serial, io, re, numpy, itertools, glob, csv
from printrun.printcore import printcore
from time import sleep
from datetime import datetime

OUTFILE='/Users/leo/data/pump-measure.csv'
MAX_SD_RATIO = 0.1
N_SAMPLES = 3
N_REPEATS = 10
MAX_DURATION = 30
# MAX_DURATION = 10
REVS = [100]
RATES = [1000, 1800]
# REVS = [10, 100, 1000]
# RATES = [10, 30, 100, 300, 1000, 1800, 3000]
# PUMPS = ['X', 'Y', 'Z']
PUMPS = ['X']
# PUMPS = ['Z']
WAIT_S = 0.3

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


def drain(sio, ser):
    while ser.inWaiting():
        sio.readline()

def read_weight(sio, ser):
    while True:
        try:
            drain(sio, ser)
            reading = sio.readline()
            match = re.search(r'([0-9.]+)g', reading, re.DOTALL)
            if match:
                print '{} read from scales: {}'.format(datetime.utcnow().isoformat(), reading)
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
    def __init__(self, rate, revs, pump, repeats):
        self.rate = rate
        self.revs = revs
        self.pump = pump
        self.repeats = repeats
        self.result = None

    @property
    def duration(self):
        return (60.0 * self.revs) / self.rate

    @property
    def forward(self):
        return 'G0 {}{} F{}'.format(self.pump, self.revs, self.rate)

    @property
    def back(self):
        return 'G0 {}-{} F{}'.format(self.pump, self.revs, self.rate)

    def __str__(self):
        return 'Test {} for {} revs at rate {} in {}s (result = {})'.format(t.pump, t.revs, t.rate, t.duration, t.result)

    __repr__ = __str__

    def run(self, sio, ser):
        self.result = {
            'pump': self.pump,
            'revs': self.revs,
            'rate': self.rate,
        }
        for rep in xrange(self.repeats):
            self.result['time'] = datetime.utcnow().isoformat()
            for command, name, sign in ((t.forward, 'forward', 1), (t.back, 'back', -1)):
#                 before = read_mean_weight(sio, N_SAMPLES, MAX_SD_RATIO)
                before = read_weight(sio, ser)
                print 'before = {}, sending "{}"'.format(before, command)
                printer.send(command)
                drain(sio, ser)
                sleep(t.duration + WAIT_S)
#                 after = read_mean_weight(sio, N_SAMPLES, MAX_SD_RATIO)
                after = read_weight(sio, ser)
#                 print 'after = {}'.format(after)
                delta = after - before
#                 print 'delta = {}'.format(delta)
                self.result['T{}_{}'.format(rep, name)] = delta * sign

print 'generating tests...'

tests = filter(lambda t: t.duration <= MAX_DURATION,
               [
                    Test(rate, revs, p, N_REPEATS)
                    for rate, revs, p in itertools.product(RATES, REVS, PUMPS)
                ])
print 'done.'
print 'opening serial port...'
with serial.Serial(
    port='/dev/tty.usbserial',
    baudrate=9600,
) as ser:
    print 'done.'
    print 'creating IOWrapper...'
    with io.TextIOWrapper(
        io.BufferedReader(ser, 1),
        newline='\r',
        errors='backslashreplace'
    ) as sio:
        print 'done.'
        usb_modem_names = glob.glob('/dev/tty.usbmodem*')
        assert len(usb_modem_names) == 1, "Too many usb modems instantiated. Can't tell which one is the Smoothieboard."
        printer_interface = usb_modem_names[0]
        print 'opening printer_interface = {} ...'.format(printer_interface)
        printer = printcore()
        printer.connect(port=printer_interface, baud=115200)
        print 'done.'
        sleep(3)
        print 'configuring Smoothie board...'
        printer.send("G91")
        print 'done.'
        print 'starting tests...'
        try:
            with open(OUTFILE,'w') as f:
                for t in tests:
                    t.run(sio, ser)
                    print t
                print 'done.'
                print 'writing results...'
                writer = csv.DictWriter(f, sorted(tests[0].result.iterkeys()))
                writer.writeheader()
                writer.writerows([t.result for t in tests])
                print 'done.'
        except Exception as e:
            print 'Exiting on error: ' + str(e)
        ser.close()
        printer.disconnect()