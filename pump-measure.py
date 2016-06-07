#!/usr/bin/env python
import serial, io, re, numpy, itertools, glob, csv, math, datetime
from printrun.printcore import printcore
from time import sleep
from datetime import datetime as dt

OUTFILE='/Users/leo/data/pump-measure.{{}}{}.csv'.format(dt.utcnow().isoformat())
PUMPS = ['Z']
BROAD_PARAMS = {
    'n_repeats': 10,
    'max_duration': 61,
    'revs': (1, 3, 10, 30, 100, 300, 600),
    'rates': (1, 3, 10, 30, 100, 300, 1000, 1800, 3000),
    'pumps': PUMPS
}
DEEP_PARAMS = {
    'n_repeats': 150,
    'max_duration': 36000,
    'revs': (0.1, 0.3, 1),
    'rates': (10, 100, 3000),
    'pumps': PUMPS
}
WAIT_S = 2.5
START_WEIGHT = 100

def read_all(sio, ser):
    read = []
    while ser.inWaiting():
        read.append(sio.readline())
    return read

def drain(sio, ser):
    read = read_all(sio, ser)
#     print 'draining done ({} lines).'.format(len(read))

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
            print '{} read from scales: {}'.format(dt.utcnow().isoformat(), readings)
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
    error = read_weight(sio, ser) - target
    while math.fabs(error) > eps:
        print "set_to_weight: error = " + str(error)
        revs = - error / MASS_PER_REV
        printer.send('G0 {}{:} F{}'.format(pump, revs, RATE))
        sleep(60 * revs / RATE + WAIT_S)
        error = read_weight(sio, ser) - target

class Test(object):
    def __init__(self, rate, revs, pump, repeats, writer_container, result_file):
        self.rate = rate
        self.revs = revs
        self.pump = pump
        self.repeats = repeats
        self.writer_container = writer_container
        self.result_file = result_file
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

    @property
    def result_writer(self):
        if not self.writer_container:
            print 'Preparing to write results to {}...'.format(self.result_file.name)
            titles = sorted(self.result.iterkeys())
            # Move the default result columns to the start 
            for title in self.default_result.iterkeys():
                titles.remove(title)
            titles = self.default_result.keys() + titles
            writer = csv.DictWriter(self.result_file, titles)
            writer.writeheader()
            print 'prepared.'
            self.writer_container.append(writer)
        return self.writer_container[0]

    def run(self, sio, ser):
        self.result = dict(self.default_result)
        set_to_weight(sio, ser, self.pump, START_WEIGHT)
        for rep in xrange(self.repeats):
            self.result['time'] = dt.utcnow().isoformat()
            start_weight = read_weight(sio, ser)
            for command, name in ((t.forward, 'F'), (t.back, 'R')):
                drain(sio, ser)
                print 'sending "{}"'.format(command)
                printer.send(command)
                sleep(t.duration + WAIT_S)
                mn, mx = read_weights(sio, ser)
                delta = mx - mn
                print 'mn = {}, mx = {}, delta = {}'.format(mn, mx, delta)
                self.result['T{:03}_{}_n'.format(rep, name)] = mn
                self.result['T{:03}_{}_x'.format(rep, name)] = mx
                self.result['T{:03}_{}_d'.format(rep, name)] = delta
            end_weight = read_weight(sio, ser)
            self.result['T{:03}_drift'.format(rep)] = end_weight - start_weight
        self.result_writer.writerow(self.result)
        self.result_file.flush()


def generate_tests(n_repeats, max_duration, revs, rates, pumps, result_file):
    writer_container = []
    tests = [
        Test(rate, revs, p, n_repeats, writer_container, result_file)
        for rate, revs, p in itertools.product(rates, revs, pumps)
    ]
    return filter(lambda t: t.duration <= max_duration, tests)

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
        try:
            for test_set_name, test_set_params in (('deep', DEEP_PARAMS), ('broad', BROAD_PARAMS)):
                with open(OUTFILE.format(test_set_name),'w') as result_file:
                    print 'generating tests...'
                    tests = generate_tests(result_file=result_file, **test_set_params)
                    runtime = sum([2 * t.repeats * (t.duration + WAIT_S) for t in tests])
                    print 'done.'
                    print 'starting {} tests (expected runtime {})...'.format(test_set_name, datetime.timedelta(seconds=runtime))
                    for t in tests:
                        t.run(sio, ser)
                        print t
                    print 'done.'
        except Exception as e:
            print 'Exiting on error: ' + str(e)
        printer.disconnect()
