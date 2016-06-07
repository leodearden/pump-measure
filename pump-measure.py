#!/usr/bin/env python
import serial, io, re, numpy, itertools, glob, csv, math, datetime, argparse, os
from printrun.printcore import printcore
from time import sleep
from datetime import datetime as dt

OUTFILE='pump-measure.{{}}{}.csv'.format(dt.utcnow().isoformat())

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

def set_to_weight(sio, ser, pump, target, wait, eps=0.1):
    MASS_PER_REV = 0.22
    RATE = 1000.0
    error = read_weight(sio, ser) - target
    while math.fabs(error) > eps:
        print "set_to_weight: error = " + str(error)
        revs = - error / MASS_PER_REV
        printer.send('G0 {}{} F{}'.format(pump, revs, RATE))
        sleep(60 * revs / RATE + wait)
        error = read_weight(sio, ser) - target

class Test(object):
    def __init__(self, rate, revs, pump, repeats, writer_container, result_file, wait_s, initial_mass):
        self.rate = rate
        self.revs = revs
        self.pump = pump
        self.repeats = repeats
        self.writer_container = writer_container
        self.result_file = result_file
        self.wait_s = wait_s
        self.initial_mass = initial_mass
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
        set_to_weight(sio, ser, self.pump, self.initial_mass, self.wait_s)
        for rep in xrange(self.repeats):
            self.result['time'] = dt.utcnow().isoformat()
            start_weight = read_weight(sio, ser)
            for command, name in ((self.forward, 'F'), (self.back, 'R')):
                drain(sio, ser)
                print 'sending "{}"'.format(command)
                printer.send(command)
                sleep(self.duration + self.wait_s)
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

def generate_tests(n_repeats, max_duration, revs, rates, pumps, result_file, args):
    writer_container = []
    tests = [
        Test(
            rate=rate,
            revs=revs,
            pump=p,
            repeats=n_repeats,
            writer_container=writer_container,
            result_file=result_file,
            wait_s=args.wait,
            initial_mass=args.initial_mass)
        for rate, revs, p in itertools.product(rates, revs, pumps)
    ]
    return filter(lambda t: t.duration <= max_duration, tests)

parser = argparse.ArgumentParser(description='Test a pump. Write the results in CSV format to one or more files.')
parser.add_argument(
    '--pump', '-p',
    help='Test this pump',
    choices=['X', 'Y', 'Z'],
    default='Z')
parser.add_argument(
    '--result-path', '-r',
    help='Write the result files to this directory. The directory must exist.',
    default='/tmp')
parser.add_argument(
    '--deep', '-d',
    help='Run the deep test suite: Get the specified number of samples for each of a small range of small volumes.',
    type=int,
    default=0)
parser.add_argument(
    '--broad', '-b',
    help='Run the broad test suite: Get the specified number of samples for each of a large range of volumes and rates.',
    type=int,
    default=10)
parser.add_argument(
    '--short', '-s',
    help='Run short versions of any requested suites, with more limited combinations of parameters.',
    action='store_true')
parser.add_argument(
    '--top-pan-balance', '-t',
    help='Read fluid mass measurements from a top pan balance connected to this serial port.',
    default='/dev/tty.usbserial')
parser.add_argument(
    '--controller', '-c',
    help='Send pump move commands to a G-code interpreter connected to this serial port. This can be a file glob.',
    default='/dev/tty.usbmodem*')
parser.add_argument(
    '--wait', '-w',
    help='Wait this many seconds after the end of the pumping operation before taking a mass measurement (to allow the top pan balance to stabilise). Can be any decimal.',
    type=float,
    default=2.5)
parser.add_argument(
    '--initial-mass', '-m',
    help='Pump this mass of material (decimal g) on to the top pan balance before starting each test (ie: before beginning to take samples with any given combination of pump revolutions and rate).',
    type=float,
    default=100)
args = parser.parse_args()

if args.short:
    broad_params = {
        'n_repeats': args.broad,
        'max_duration': 21,
        'revs': (1, 10, 100),
        'rates': (10, 100, 1000, 3000),
        'pumps': [args.pump]
    }
    deep_params = {
        'n_repeats': args.deep,
        'max_duration': 3600,
        'revs': (0.3, 1),
        'rates': (100, 3000),
        'pumps': [args.pump]
    }
else:
    broad_params = {
        'n_repeats': args.broad,
        'max_duration': 61,
        'revs': (1, 3, 10, 32, 100, 320, 600),
        'rates': (1, 3, 10, 32, 100, 320, 560, 1000, 1300, 1800, 2400, 3000),
        'pumps': [args.pump]
    }
    deep_params = {
        'n_repeats': args.deep,
        'max_duration': 36000,
        'revs': (0.1, 0.3, 1),
        'rates': (10, 100, 3000),
        'pumps': [args.pump]
    }

print 'opening serial port...'
with serial.Serial(
    port=args.top_pan_balance,
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
        usb_modem_names = glob.glob(args.controller)
        assert len(usb_modem_names) > 0, "No Smoothieboard found. Try '--controller=<controller_port>'?"
        assert len(usb_modem_names) == 1, "More than one file matches. Can't tell which one is the Smoothieboard."
        printer_interface = usb_modem_names[0]
        print 'opening printer_interface = {} ...'.format(printer_interface)
        printer = printcore()
        printer.connect(port=printer_interface, baud=115200)
        print 'done.'
        sleep(3)
        print 'configuring Smoothie board...'
        printer.send("G91")
        print 'done.'
        for test_set_name, test_set_params in (('deep', deep_params), ('broad', broad_params)):
            result_file_name = os.path.join(args.result_path, OUTFILE.format(test_set_name))
            if test_set_params['n_repeats']:
                with open(result_file_name,'w') as result_file:
                    print 'generating {} tests...'.format(test_set_name)
                    tests = generate_tests(args=args, result_file=result_file, **test_set_params)
                    runtime = sum([2 * t.repeats * (t.duration + t.wait_s) for t in tests])
                    print 'done.'
                    print 'starting {} tests (expected runtime {})...'.format(test_set_name, datetime.timedelta(seconds=runtime))
                    for t in tests:
                        t.run(sio, ser)
                        print t
                    print 'done.'
        printer.disconnect()
