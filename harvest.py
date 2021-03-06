#!/usr/bin/env python

import sys
import re
import getopt
import ftplib
import pandas as pd
import numpy as np
import gzip
from ftplib import FTP
from sqlalchemy import create_engine
from sqlalchemy_utils.functions import create_database, database_exists


def fetch_data_via_ftp():
    ftp = FTP('ftp.nass.usda.gov')
    ftp.login()
    ftp.cwd('quickstats')

    files = []

    try:
        files = ftp.nlst()
    except ftplib.error_perm, resp:
        if str(resp) == "550 No files found":
            print "No files in this directory"
        else:
            raise

    crops_file = [f for f in files if re.match('^qs.crops_', f)][0]

    ftp.retrbinary('RETR ' + crops_file, open('nass_crops.csv.gz', 'wb').write)
    ftp.quit()
    print 'Done downloading the crops file'


def read_file(start_date, end_date):
    dataframe = pd.read_csv(gzip.open('nass_crops.csv.gz'), sep='\t')

    start_year = int(start_date[:4])
    end_year = int(end_date[:4])

    columns = ['DOMAIN_DESC', 'COMMODITY_DESC', 'GROUP_DESC', 'STATISTICCAT_DESC', 'AGG_LEVEL_DESC', 'COUNTRY_NAME', 'STATE_NAME', 'COUNTY_NAME', 'UNIT_DESC', 'VALUE', 'YEAR']
    dataframe = dataframe[columns]

    filtered_dataframe = dataframe[(dataframe.YEAR >= start_year) & (dataframe.YEAR <= end_year)]

    return filtered_dataframe


def write_dataframe_to_db(dataframe, database_host, database_name, database_user, database_password, port, table):
    # create database
    connection_string = "postgres://" + database_user + ":" + database_password + "@" + database_host + ":" + str(port)
    engine = create_engine(connection_string)

    if not database_exists(connection_string + '/' + database_name):
        create_database(connection_string + '/' + database_name)

    dataframe.to_sql(table, engine, if_exists='replace')


def run_analysis(dataframe):
    # clean the dataframe
    dataframe.replace(['(D)', '(Z)', '(NA)'], np.NaN, inplace=True)
    dataframe['VALUE'] = dataframe.VALUE.str.replace(',', '').astype(float)  # convert comma delimited numbers to float

    # How many datapoints do we have:
    datapoints = str(len(dataframe))
    print "******************************************"
    print "The number of data points: " + datapoints

    # Commodities value counts:
    commodity_value_counts = dataframe.COMMODITY_DESC.value_counts()
    print commodity_value_counts

    # State value counts
    state_value_counts = dataframe.STATE_NAME.value_counts()
    print "******************* STATE VALUE COUNTS *********************"
    print state_value_counts

    # Barley Analysis
    barley_df = dataframe[(dataframe['AGG_LEVEL_DESC'] == 'COUNTY') & (dataframe['COMMODITY_DESC'] == 'BARLEY')]

    try:
        barley_dict = dict(barley_df.sort_values('VALUE', ascending=False).iloc[0])
    except IndexError:
        pass
    else:
        county_name = barley_dict['COUNTY_NAME']
        barley_value = barley_dict['VALUE']
        barley_year = barley_dict['YEAR']
        print "******************************************"
        print "The highest barley production: BY " + county_name + " in the year " + str(barley_year) + " at " + str(barley_value) + " Acres"

    # Horticulture Analysis
    horticulture_df = dataframe[(dataframe['AGG_LEVEL_DESC'] == 'NATIONAL') & (dataframe['GROUP_DESC'] == 'HORTICULTURE')]

    try:
        horticulture_dict = dict(horticulture_df.sort_values('VALUE', ascending=False).iloc[0])
    except IndexError:
        pass
    else:
        horticulture_value = horticulture_dict['VALUE']
        horticulture_year = horticulture_dict['YEAR']
        print "******************************************"
        print "The highest horticulture nationally was in the year " + str(horticulture_year) + " at " + str(horticulture_value) + " Acres"

    # create a dataframe with some analysis data
    analysis_dataframe = pd.DataFrame({'datapoints_number': datapoints, 'commodity_value_count': str(commodity_value_counts),
                                       'state_value_count': str(state_value_counts)}, index=[0])
    return analysis_dataframe


def begin_nass_harvest(database_host, database_name, database_user, database_password,
                       port, start_date, end_date):
    print "Run 'python harvest.py -h' for help\n\n"

    print "Supplied Args (some default): "
    print "Database Host: {}".format(database_host)
    print "Database Name: {}".format(database_name)
    print "Database Username: {}".format(database_user)
    print "Database Password: {}".format(database_password)
    print "Database Port (hard-coded): {}".format(port)
    print "Harvest Start Date: {}".format(start_date)
    print "Harvest End Date: {}\n".format(end_date)

    print "Started Fetching data...."
    print "This might take a while. Grab yourself some coffee."
    fetch_data_via_ftp()
    print "*********** DONE FETCHING DATA **************"

    print "Reading data into a dataframe..."
    dataframe = read_file(start_date, end_date)
    print "*********** DONE READING DATA **************"

    print "Writing data to database"
    write_dataframe_to_db(dataframe, database_host, database_name, database_user, database_password, port, 'fact_data')
    print "*********** DONE WRITING DATA **************"

    print "Some analysis on the data"
    print "---------------------------------------------"
    analysis_dataframe = run_analysis(dataframe)
    write_dataframe_to_db(analysis_dataframe, database_host, database_name, database_user, database_password, port, 'stats')
    print "Some analysis has been written into the stats table"
    print "*********** DONE RUNNING THE harvest PACKAGE! ***********"


def main(argv):
    try:
        opts, args = getopt.getopt(argv, "h", ["database_host=", "database_name=", "start_date=",
                                               "database_user=", "database_pass=", "end_date="])
    except getopt.GetoptError:
        print 'Flag error. Probably a mis-typed flag. Make sure they start with "--". Run python ' \
              'harvest.py -h'
        sys.exit(2)

    # define defaults
    database_host = 'localhost'
    database_name = 'gro'
    port = 5432
    database_user = 'gro'
    database_password = 'gro123'
    start_date = '2005-1-1'
    end_date = '2015-12-31'

    for opt, arg in opts:
        if opt == '-h':
            print "\nThis is my harvest script for the Gro Hackathon NASS harvest"
            print '\nExample:\npython harvest.py --database_host localhost --database_name gro2\n'
            print '\nFlags (all optional, see defaults below):\n ' \
              '--database_host [default is "{}"]\n ' \
              '--database_name [default is "{}"]\n ' \
              '--database_user [default is "{}"]\n ' \
              '--database_pass [default is "{}"]\n ' \
              '--start_date [default is "{}"]\n ' \
              '--end_date [default is "{}"]\n'.format(database_host, database_name, database_user,
                                                      database_password, start_date, end_date)
            sys.exit()
        elif opt in ("--database_host"):
            database_host = arg
        elif opt in ("--database_name"):
            database_name = arg
        elif opt in ("--database_user"):
            database_user = arg
        elif opt in ("--database_pass"):
            database_password = arg
        elif opt in ("--start_date"):
            start_date = arg
        elif opt in ("--end_date"):
            end_date = arg

    begin_nass_harvest(database_host, database_name, database_user, database_password,
                       port, start_date, end_date)

if __name__ == "__main__":
    main(sys.argv[1:])

