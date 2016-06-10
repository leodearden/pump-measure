#!/usr/bin/env python
import serial, io, re, numpy, itertools, glob, csv, math, datetime, argparse, os, logging
from printrun.printcore import printcore
from time import sleep, time
from datetime import datetime as dt
from types import MethodType

OUTFILE='pump-measure.{{}}.{}.csv'.format(dt.utcnow().isoformat())
log = logging.getLogger('pm')
log.setLevel(logging.DEBUG)

def rsleep(sleep_s):
    RELATIVE_CORRECTION = 0.8
    EPS = 0.01
    DEBUG_RELATIVE_ERR = 0.05
    WARN_RELATIVE_ERR = 0.19
    now_s = time()
    target_s = now_s + sleep_s
    while now_s + EPS < target_s:
        sleep_command_s = (target_s - now_s) * RELATIVE_CORRECTION
        before_s = time()
        sleep(sleep_command_s)
        now_s = time()
        sleep_actual_s = now_s - before_s
        relative_err = sleep_actual_s / sleep_command_s - 1
        if math.fabs(relative_err) > WARN_RELATIVE_ERR:
            log.warn('Very inaccurate sleep (command = {}s, actual = {}s, relative err = {})'.format(sleep_command_s, sleep_actual_s, relative_err))
        elif math.fabs(relative_err) > DEBUG_RELATIVE_ERR:
            log.debug('Inaccurate sleep (command = {}s, actual = {}s, relative err = {})'.format(sleep_command_s, sleep_actual_s, relative_err))

def read_all(sio, ser, at_least_one=False):
    read = []
    keepNextLine = True
    while ser.inWaiting() or (at_least_one and not read):
        try: 
            line = sio.readline()
            if keepNextLine:
                read.append(line)
            else:
                log.debug('Discarding potentially corrupt or incomplete line ({})'.format(line))
                keepNextLine = True
        except TypeError as e:
            log.warn('Caught TypeError ({}) when trying to read from top pan balance. Draining raw input and discarding next line.'.format(str(e)))
            drained = ser.read(100000)
            log.debug('Drained {} raw characters ({}).'.format(len(drained), drained))
            keepNextLine = False
    return read

def drain(sio, ser):
    read = read_all(sio, ser)

def parse_weight(reading):
    match = re.search(r'([0-9.]+)g', reading, re.DOTALL)
    if match:
        return float(match.group(1))
    else:
        return None

def read_weights(sio, ser):
    while True:
        try:
            log.debug('about to read from balance...')
            readings = read_all(sio, ser, at_least_one=True)
            log.debug('{} read from balance: {}'.format(dt.utcnow().isoformat(), readings))
            values = []
            for reading in readings:
                weight = parse_weight(reading)
                if weight:
                    values.append(weight)
                else:
                    log.warn("couldn't parse printer message: '{}'".format(reading))
            return min(values), max(values)
        except serial.SerialException as e:
            log.info('SerialException on read ({}). Trying again.'.format(e))
            continue

def read_weight(sio, ser):
    drain(sio, ser)
    readings = []
    readings = read_all(sio, ser, at_least_one=True)
    assert readings
    return parse_weight(readings[-1])

def set_to_weight(sio, ser, pump, target, wait, eps=0.1):
    log.debug('set_to_weight: target = ' + str(target))
    MASS_PER_REV = 0.2
    RATE = 1000.0
    error = read_weight(sio, ser) - target
#    while math.fabs(error) > eps:
    log.debug("set_to_weight: initial error = " + str(error))
    revs = - error / MASS_PER_REV
    printer.send('G0 {}{} F{}'.format(pump, revs, RATE))
    sleep_time_s = 60 * math.fabs(revs) / RATE + wait
    log.debug('set_to_weight: about to sleep for {}s'.format(sleep_time_s))
    rsleep(sleep_time_s)
    error = read_weight(sio, ser) - target
    log.info("set_to_weight: final error = " + str(error))


def test_set_to_weight(sio, ser, pump, wait):
    origin = 150
    mn = 50
    set_to_weight(sio, ser, pump, origin, wait)
    a = 0.5
    b = 1
    while a < (origin - mn):
        set_to_weight(sio, ser, pump, origin + a, wait)
        set_to_weight(sio, ser, pump, origin - a, wait)
        a, b = b, a + b

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
            log.debug('Preparing to write results to {}...'.format(self.result_file.name))
            titles = sorted(self.result.iterkeys())
            # Move the default result columns to the start 
            for title in self.default_result.iterkeys():
                titles.remove(title)
            titles = self.default_result.keys() + titles
            writer = csv.DictWriter(self.result_file, titles)
            writer.writeheader()
            log.debug('prepared.')
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
                log.debug('sending "{}"'.format(command))
                printer.send(command)
                rsleep(self.duration + self.wait_s)
                mn, mx = read_weights(sio, ser)
                delta = mx - mn
                log.debug('mn = {}, mx = {}, delta = {}'.format(mn, mx, delta))
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

def estimate_runtime(tests):
    runtime = sum([2 * t.repeats * (t.duration + t.wait_s) for t in tests])
    formatted_time_remaining = datetime.timedelta(seconds=runtime)
    return formatted_time_remaining

def patched_send(self, command, lineno = 0, calcchecksum = False):
    # Only add checksums if over serial (tcp does the flow control itself)
    if calcchecksum and not self.printer_tcp:
        prefix = "N" + str(lineno) + " " + command
        command = prefix + "*" + str(self._checksum(prefix))
        if "M110" not in command:
            self.sentlines[lineno] = command
    if self.printer:
        if self.writefailures > 3:
            self.logError(_(u"Too many failures to write to printer. Bouncing connection."))
            self.disconnect()
            self.connect()
        self.sent.append(command)
        # run the command through the analyzer
        gline = None
        try:
            gline = self.analyzer.append(command, store = False)
        except:
            logging.warning(_("Could not analyze command %s:") % command +
                            "\n" + traceback.format_exc())
        if self.loud:
            logging.info("SENT: %s" % command)
        if self.sendcb:
            try: self.sendcb(command, gline)
            except: self.logError(traceback.format_exc())
        try:
            self.printer.write(str(command + "\n"))
            if self.printer_tcp:
                try:
                    self.printer.flush()
                except socket.timeout:
                    pass
            self.writefailures = 0
        except socket.error as e:
            if e.errno is None:
                self.logError(_(u"Can't write to printer (disconnected ?):") +
                              "\n" + traceback.format_exc())
            else:
                self.logError(_(u"Can't write to printer (disconnected?) (Socket error {0}): {1}").format(e.errno, decode_utf8(e.strerror)))
            self.writefailures += 1
        except SerialException as e:
            self.logError(_(u"Can't write to printer (disconnected?) (SerialException): {0}").format(decode_utf8(str(e))))
            self.writefailures += 1
        except RuntimeError as e:
            self.logError(_(u"Socket connection broken, disconnected. ({0}): {1}").format(e.errno, decode_utf8(e.strerror)))
            self.writefailures += 1

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
    '--skip',
    help='Skip this many tests',
    type=int,
    default=0)
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
parser.add_argument(
    '--test-origin', '-o',
    help='Test script functionality for setting the mass in the balance. Test passes if run completes without reported error.',
    action='store_true')
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
        'revs': (0.1, 0.3, 1),
        'rates': (100),
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

log.debug('opening serial port...')
with serial.Serial(
    port=args.top_pan_balance,
    baudrate=9600,
    timeout=0.5
) as ser:
    log.debug('done.')
    log.debug('creating IOWrapper...')
    with io.TextIOWrapper(
        io.BufferedReader(ser, 1),
        newline='\r',
        errors='backslashreplace'
    ) as sio:
        log.debug('done.')
        usb_modem_names = glob.glob(args.controller)
        assert len(usb_modem_names) > 0, "No Smoothieboard found. Try '--controller=<controller_port>'?"
        assert len(usb_modem_names) == 1, "More than one file matches. Can't tell which one is the Smoothieboard."
        printer_interface = usb_modem_names[0]
        log.debug('opening printer_interface = {} ...'.format(printer_interface))
        printer = printcore()
        printer._send = MethodType(patched_send, printer)
        printer.connect(port=printer_interface, baud=115200)
        log.debug('done.')
        rsleep(3)
        printer.send("G91")
        if args.test_origin:
            test_set_to_weight(sio, ser, args.pump, args.wait)
        for test_set_name, test_set_params in (('deep', deep_params), ('broad', broad_params)):
            result_file_name = os.path.join(args.result_path, OUTFILE.format(test_set_name))
            if test_set_params['n_repeats']:
                with open(result_file_name,'w') as result_file:
                    log.debug('generating {} tests...'.format(test_set_name))
                    tests = generate_tests(args=args, result_file=result_file, **test_set_params)
                    log.debug('done.')
                    log.info('starting {} tests ({} parameter combinations, expected runtime {})...'.format(test_set_name, len(tests), estimate_runtime(tests)))
                    for i, t in [(i, t) for i, t in enumerate(tests) if i >= args.skip]:
                        log.debug('starting test {} of {}, estimated remaining runtime {}'.format(i+1, len(tests), estimate_runtime(tests[i:])))
                        t.run(sio, ser)
                        log.debug('test {} of {} complete: \n{}'.format(i+1, len(tests), str(t)))
                    log.info('done.')
        printer.disconnect()
