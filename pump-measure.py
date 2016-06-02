#!/usr/bin/env python
import serial, io, re, numpy, itertools, glob, csv, math
from printrun.printcore import printcore
from time import sleep
from datetime import datetime

OUTFILE='/Users/leo/data/pump-measure.csv'
N_REPEATS = 10
MAX_DURATION = 61
REVS = [1, 3, 10, 30, 100, 300, 600]
RATES = [1, 3, 10, 30, 100, 300, 1000, 1800, 3000]
# REVS = [30, 100]
# RATES = [1800, 3000]
PUMPS = ['X']
WAIT_S = 2.0
START_WEIGHT = 100

def read_all(sio, ser):
    read = []
    while ser.inWaiting():
        read.append(sio.readline())
    return read

def drain(sio, ser):
    read = read_all(sio, ser)
    print 'draining done ({} lines).'.format(len(read))

def parse_weight(reading):
                match = re.search(r'([0-9.]+)g', reading, re.DOTALL)
                if match:
                    return float(match.group(1))
                else:
                    return None

def read_weights(sio, ser):
    while True:
        try:
            print 'about to read from balance...'
            readings = read_all(sio, ser)
            print '{} read from scales: {}'.format(datetime.utcnow().isoformat(), readings)
            values = []
            for reading in readings:
                weight = parse_weight(reading)
                if weight:
                    values.append(weight)
                else:
                    print "couldn't parse printer message: '{}'".format(reading)
            return min(values), max(values)
        except serial.SerialException as e:
            #There is no new data from serial port
            print 'trying again to read'
            continue

def read_weight(sio, ser):
    drain(sio, ser)
    readings = []
    while not readings:
        readings = read_all(sio, ser)
    return parse_weight(readings[-1])

def set_to_weight(sio, ser, pump, target, eps=0.1):
    MASS_PER_REV = 0.22
    RATE = 1000
    weight = read_weight(sio, ser)
    while math.fabs(target - weight) > eps:
        print "Error = " + str(target - weight)
        revs = (target - weight) / MASS_PER_REV
        printer.send('G0 {}{} F{}'.format(pump, revs, RATE))
        sleep(WAIT_S)
        weight = read_weight(sio, ser)

class Test(object):
    def __init__(self, rate, revs, pump, repeats):
        self.rate = rate
        self.revs = revs
        self.pump = pump
        self.repeats = repeats
        self.result = None
        self.default_result = {
            'pump':self.pump, 
            'revs':self.revs, 
            'rate':self.rate,
            'time':None,}

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
        self.result = dict(self.default_result)
        set_to_weight(sio, ser, self.pump, START_WEIGHT)
        for rep in xrange(self.repeats):
            self.result['time'] = datetime.utcnow().isoformat()
            start_weight = read_weight(sio, ser)
            for command, name in ((t.forward, 'forward'), (t.back, 'back')):
                drain(sio, ser)
                print 'sending "{}"'.format(command)
                printer.send(command)
                sleep(t.duration + WAIT_S)
                mn, mx = read_weights(sio, ser)
                delta = mx - mn
                print 'mn = {}, mx = {}, delta = {}'.format(mn, mx, delta)
                self.result['T{}_{}_min'.format(rep, name)] = mn
                self.result['T{}_{}_max'.format(rep, name)] = mx
                self.result['T{}_{}_delta'.format(rep, name)] = delta
            end_weight = read_weight(sio, ser)
            self.result['T{}_drift'.format(rep)] = end_weight - start_weight

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
                titles = sorted(tests[0].result.iterkeys())
                for title in t.default_result.iterkeys():
                    titles.remove(title)
                titles = t.default_result.keys() + titles
                writer = csv.DictWriter(f, titles)
                writer.writeheader()
                writer.writerows([t.result for t in tests])
                print 'done.'
        except Exception as e:
            print 'Exiting on error: ' + str(e)
        printer.disconnect()