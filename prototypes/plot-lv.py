# Plots a longitude velocity diagram for the MAGMO observations.
# This program will scan all votable files in the current directory
# extract the longitude, velocity and opacity data from each file
# and then plot it on a longitude-velocity diagram

# Author: James Dempsey

from astropy.io.votable import parse
import numpy as np
import matplotlib.pyplot as plt
import glob


def createSampleData():
    np.random.seed(0)
    n = 10000
    x = 360 * np.random.random(n) - 180
    y = np.random.random(n) * 100/180 * (180 - np.abs(x)) * (-x/abs(x))
    c = 1 - (np.random.random(n) * ((180 - np.abs(x)) / 180) )#* ((100 - np.abs(y))/100))
    return x, y, c


def readData():
    x = []
    y = []
    c = []

    bad_spectra = 0
    prev_field = ''
    num_fields = 0
    vo_files = glob.glob('day*/*.votable.xml')
    for filename in sorted(vo_files):
        print 'Reading', filename
        votable = parse(filename, pedantic=False)
        results = next(resource for resource in votable.resources if resource.type == "results")
        if results is not None:
            gal_info = None
            for info in votable.infos:
                if info.name == 'longitude':
                    gal_info = info
            #gal_info = votable.get_info_by_id('longitude')
            if gal_info is None:
                print "No longitude provided for %s, skipping" % filename
                continue
            gal_long = float(gal_info.value)
            if gal_long > 180:
                gal_long -= 360
            results_array = results.tables[0].array
            poor_sn = False
            #print gal_long
            for row in results_array:
                opacity = row['opacity']
                if opacity > 6 or opacity < -8:
                    poor_sn = True
            if not poor_sn:
                for row in results_array:
                    x.append(gal_long)
                    y.append(row['velocity']/1000.0) # Convert from m/s to km/s
                    opacity = row['opacity']
                    c.append(opacity)
                    if opacity > 10 or opacity < -15:
                        poor_sn = True
                field = filename.split('_')
                if field[0] != prev_field:
                    prev_field = field[0]
                    num_fields += 1
            if poor_sn:
                bad_spectra += 1

    print "In %d fields read %d spectra of which %d had reasonable S/N. " % (
        num_fields, len(vo_files), len(vo_files)-bad_spectra)
    return x, y, c


def plot(x, y, c, filename):
    xmin=-180
    xmax = 180
    ymin = -300
    ymax = 300

    val = np.clip(c, -0.005, 1.05)
    #print val
    fig = plt.figure(1, (12,6))
    # plt.subplots_adjust(hspace=0.5)
    plt.subplot(111, axisbg='black')
    plt.hexbin(x, y, val, cmap=plt.cm.gist_heat_r)
    # plt.scatter(x, y, cmap=plt.cm.YlOrRd_r)
    plt.axis([xmax, xmin, ymin, ymax])
    plt.title("Longitude-Velocity")
    plt.xlabel('Galactic longitude (l)')
    plt.ylabel('LSR Velocity (km/s)')
    cb = plt.colorbar()
    cb.set_label(r'$e^{(-\tau)}$')

    #plt.subplot(122)
    #plt.hexbin(x, y, c, bins='log', cmap=plt.cm.YlOrRd_r)
    #plt.axis([xmin, xmax, ymin, ymax])
    #plt.title("With a log color scale")
    #cb = plt.colorbar()
    #cb.set_label('log10(N)')

    plt.savefig(filename)

    # plt.show()
    return

## Script starts here
#x, y, c = createSampleData()
x, y, c = readData()
plot(x, y, c, 'magmo-lv.pdf')