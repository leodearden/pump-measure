#!/usr/bin/env python
import numpy, csv, argparse
import matplotlib.pyplot as plt
import itertools


def extract_data(d, measurements):
    data = {
        (float(r['revs']), float(r['rate'])): {
            name:[
                float(r[k])
                for k in r.keys()
                if k[-3:] == suffix
            ]
            for suffix, name in measurements
        }
        for r in d
    }
    return data

parser = argparse.ArgumentParser(description='Analyse and plot from a pump-measure results file.')
parser.add_argument(
    'input_file',
    help='The path to the input .csv, as generated by pump-measure.py')
parser.add_argument(
    '--histogram',
    help='Plot histograms',
    action='store_true')
parser.add_argument(
    '--time-series', '-t',
    help='Plot time (ordinal) series',
    action='store_true')
args = parser.parse_args()

print 'Analysing {}'.format(args.input_file)
df = open(args.input_file)
dr = csv.DictReader(df)
d = list(dr)
# Parse data into JSONable structure
measurements = (('F_d', 'forward'), ('R_d', 'reverse'))
data = extract_data(d, measurements)

all_revs = sorted(set([rev for rev, _ in data.iterkeys()]))
all_rates = sorted(set([rate for _, rate in data.iterkeys()]))

measurement_names = [name for _, name in measurements]
colours = ['r', 'g', 'b']

figs = {}
axiess = {}
figs[name], axiess[name] = plt.subplots(nrows=len(all_revs),
                                        ncols=len(all_rates),
                                        sharex=True)
figs[name].suptitle(name)
for i, revs in enumerate(all_revs, 0):
    all_relevant_data = sum(
        [
            data.get((revs, rate), {name:[]})[name]
            for rate in all_rates],
        [])
    min_datum = min(
        all_relevant_data)
    max_datum = max(
        all_relevant_data)
    for j, rate in enumerate(all_rates, 0):
        print 'looking for ({}, {})'.format(revs, rate)
        axis = axiess[name][i][j]
        if (revs, rate) in data:
            plot_params = zip(
                numpy.array([
                    range(len(data[revs, rate][name]))
                    for name in measurement_names
                ]),
                numpy.array([
                    data[revs, rate][name]
                    for name in measurement_names
                ]),
                colours)
            title = '{}, {}'.format(str(revs), str(rate))
            print "charting " + title
            axis.set_ylim(min_datum, max_datum)
            if args.histogram:
                axis.hist(*plot_params, normed=True)
            if args.time_series:
                for x, y, format in plot_params:
                    axis.plot(x, y, format)
            axis.set_title(title)
        else:
            axis.set_visible(False)

plt.show()