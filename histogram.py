import numpy, csv
import matplotlib.pyplot as plt
from numpy.random import normal

# gaussian_numbers = normal(size=1000)
# plt.hist(gaussian_numbers)
# plt.title("Gaussian Histogram")
# plt.xlabel("Value")
# plt.ylabel("Frequency")
# plt.show()

df = open('pump-measure.deep2016-05-27T14-49-17.091206.csv')
dr = csv.DictReader(df)
d = list(dr)
for r in d:
    plt.hist(numpy.array([float(r[k]) for k in r.keys() if (k[-3:] == 'F_d')]), normed=True)
    plt.title(str(r['revs']) + ' ' + str(r['rate']))
    plt.show()