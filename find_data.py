# Script to query ATOA to find the RPFITS files representing a day's observations.
# Each file is then downloaded.
# Note in the future, an interface will be provided in ATOA to allow a list of file
# urls which do not require login to be downloaded and then used in a tool such as
# wget,

# Author: James Dempsey
# Date: 6 August, 2016

import magmo
import os
import sys
import time
# REST requests
import urllib, urllib2, base64
# VO Table parsing
from astropy.io import votable
# For hidden entry of password
import getpass
import re
import requests

# Constants
atoa_tap_url = 'http://atoavo.atnf.csiro.au/tap/sync'
atoa_login_url = 'http://atoa.atnf.csiro.au/login'
atoa_download_service = 'http://atoa.atnf.csiro.au/RPFITS'

obs_prog_id = 'C2291'

# Block size to be read at a time in bytes
chunk_size = 4 * 1024


def adql_query(url, query_string, filename, username=None, password=None, file_write_mode='w'):
    """
    Run an ADQL query and write the resulting VO Table to a file.

    :param url: The url of the sync endpoint of the TAP service
    :param query_string: The ADQL query to be run
    :param filename: The name of the file where the result is to be saved in votable format.
    :param username: The username to use, if authentication is needed
    :param password: The password to use, if authentication is needed
    :param file_write_mode: The write mode to be used when opening the output file.
    :return: None
    """
    req = urllib2.Request(url)
    # Uses basic auth to securely access the data access information for the image cube
    if username is not None:
        base64string = base64.encodestring('%s:%s' % (username, password)).replace('\n', '')
        req.add_header("Authorization", "Basic %s" % base64string)
    data = urllib.urlencode({'query': query_string, 'request': 'doQuery', 'lang': 'ADQL', 'format': 'votable'})
    u = urllib2.urlopen(req, data)
    queryResult = u.read()
    # Short term workaround for the field type being incorrect
    queryResult = re.sub('character varying\([0-9]+\)', 'char" arraysize="*', queryResult)
    with open(filename, file_write_mode) as f:
        f.write(queryResult)


def query_atoa(day_row):
    """
    Build and run an ADQL query to retrieve the list of a day's MAGMO observations
    from ATOA. This is restricted to only the files with HI data. The query result
     will be stored in a temp directory in the current working directory.

    :param day_row: The config row for the day, this defines the filename patterns
    :return: A list of the obs_id values for the day's observations.
    """
    obs_ids = []
    base_query = "SELECT distinct obs_id, access_url " \
                 + "FROM ivoa.obscore where obs_collection = 'C2291' " + \
                 "and frequency in (1421.0, 1420.5) and data_flag < 999 "

    temp_dir = 'temp'
    magmo.ensure_dir_exists(temp_dir)
    temp_file = temp_dir + "/query-result.xml"
    day_select = ' and ('
    for i in range(2, len(day_row)):
        if i > 2:
            day_select += ' or '
        day_select += "obs_id like '" + day_row[i] + "%." + obs_prog_id + "'"
    day_select += ')'
    query = base_query + day_select + " order by 1"

    adql_query(atoa_tap_url, query, temp_file)
    result_votable = votable.parse(temp_file, pedantic=False)
    results = result_votable.get_first_table().array
    for row in results:
        # obs_id = row['access_url']
        obs_id = row['obs_id']
        # print obs_id
        if obs_id is not None:
            obs_ids.append(obs_id)

    return obs_ids


def is_obs_cal_only(obs_id):
    """
    Identify if the supplied observation is an observatio of a single bandpass
    calibration. Where these occur at the start of an observing run they may be
    junk data recording the pahse adjustment process.
    :param obs_id: The id of the observation to be checked.
    :return: True if the observation file only includes a single cal source, False otherwise
    """
    query = """select obs_id
        from ivoa.obscore
        where obs_collection = '{0}' and obs_id = '{1}'
        group by obs_id
        having count(distinct target_name) = 1
        and min(target_name) in ('1934-638', '0823-500')""".format(obs_prog_id, obs_id)

    temp_dir = 'temp'
    magmo.ensure_dir_exists(temp_dir)
    temp_file = temp_dir + "/cal-result.xml"
    adql_query(atoa_tap_url, query, temp_file)

    result_votable = votable.parse(temp_file, pedantic=False)
    result = result_votable.get_first_table().array
    return len(result) > 0


def login_to_atoa(userid, password):
    """
    Establish an authenticated session with the ATOA web server.

    :param userid: The OPAL user id to be used.
    :param password: The OPAL password to be used.
    :return: The session to be used for future authenticated interaction with ATOA.
    """
    session = requests.session()

    # This is the form data that the page sends when logging in
    login_data = {
        'j_username': userid,
        'j_password': password,
        'submit': 'Login',
        '_action': 'login',
    }

    # Authenticate
    r = session.post(atoa_login_url, data=login_data)
    if r.status_code != 200:
        print r.headers
    return session


def get_download_urls(obs_ids, session):
    """
    Retrieve a list of URLs which can be used to download the listed observations.
    The URLs can then be used in standard download tools such as wget.

    :param obs_ids: The ids of the observations which are to be retrieved.
    :param session: The authenticated ATOA web session.
    :return: A list of URLs, one for reach observation.
    """
    data = ''
    for id in obs_ids:
        data += id + '\n'
    print data
    form_data = {'filelist': data, 'bundle': 'textlist'}
    r = session.post(atoa_download_service, data=form_data)
    urls = r.text

    return urls


def download_files(urls, session):
    """
    Download a set of observation files from ATOA. This may be the access_url
    values for the observation whcih require use of an authenticated session,
    or the download URLs which do not require further authentication. Note
    that downloading via tools such as wget using the pre-authenticated URLs
    will generally be much faster than using this method.

    :param urls: The URLs of the observations.
    :param session: The authenticated web session with ATOA.
    :return: None
    """
    for url in urls:
        filename = 'rawdata/' + url[url.find('fname') + 6:]

        if os.path.exists(filename):
            print 'Skipping existing file ', filename
        else:
            print 'Downloading file ', filename
            r = session.get(url, stream=True)
            with open(filename, 'wb') as fd:
                for chunk in r.iter_content(chunk_size):
                    fd.write(chunk)


def main():
    # Read input parameters
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("Incorrect number of parameters.")
        print("Usage: python find_data.py day userid [passwordfile]")
        exit(1)
    day = sys.argv[1]
    userid = sys.argv[2]
    password = None
    if len(sys.argv) > 3:
        with open(sys.argv[3], 'r') as fd:
            password = fd.readlines()[0].strip()
    else:
        password = getpass.getpass("Enter your OPAL password: ")

    start = time.time()

    day_row = magmo.get_day_file_data(day)
    if day_row is None:
        print "Day %s is not defined." % (day)
        exit(1)
    print "#### Started finding data for MAGMO day %s at %s ####" % \
          (day, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start)))
    print day_row

    # Query ATOA for desired ids
    obs_ids = query_atoa(day_row)
    if len(obs_ids) > 0 and is_obs_cal_only(obs_ids[0]):
        print "Ignoring cal only first obs: ", obs_ids[0]
        obs_ids = obs_ids[1:]

    session = login_to_atoa(userid, password)
    # download_files(obs_ids, session)
    urls = get_download_urls(obs_ids, session)

    url_filename = 'filelist/day' + day + '.txt'
    with open(url_filename, 'wb') as uf:
        uf.write(urls)

    print "Urls written to %s " % (url_filename)

    # Report
    end = time.time()
    print '#### File discovery completed at %s ####' \
          % (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end)))
    print 'Processed in %.02f s' % (end - start)
    exit(0)


# Run the script if it is called from the command line
if __name__ == "__main__":
    main()
