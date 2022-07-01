#!/usr/bin/python3
# -*- coding: latin-1 -*-

# COPYRIGHT
# © 2022 Hitachi Vantara LLC. All rights reserved.

import requests
import json
import os, sys, shutil
import base64
import http.client
import argparse
import warnings
import pandas as pd
import numpy as np
from itertools import cycle
from shutil import get_terminal_size
from threading import Thread
from time import sleep
from datetime import datetime
from datetime import timedelta


# ### Parsing arguments ################################# #

examples = '''examples:
  {prog}                    : Collects the data of the last completed month
  {prog} -y 2022            : Collects the data of the last completed month of 2022
  {prog} -m 2               : Collects the data of 2nd month of this year
  {prog} -day 22            : Collects the data of 22nd day of the last completed month
  {prog} -month 2 -d 22     : Collects the data of February 2nd this year
  {prog} -m 2 -year 2022    : Collects the data of February this year
  {prog} -d 2 -m 2 -y 2022  : Collects the data of 2nd February 2022
'''.format(prog="hvCollect.py")

def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(prog="hvCollect.py", description='Use the ' + "hvCollect.py" + ' command to collect data for reporting.', epilog=examples, formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False)

    parser.add_argument('-help', '-h', action='help', default=argparse.SUPPRESS, help='Show this help message and exit.')
    parser.add_argument('-version', '-v', action='version', version='%(prog)s ' + hitachiConfig['version'], help='Show program\'s version number and exit.')

    group_main = parser.add_argument_group("usage")
    group_main.add_argument('-day', '-d', type=int, metavar='<DAY>', help='(Optional) Specify the day of the data you want to collect.')
    group_main.add_argument('-month', '-m', type=int, metavar='<MONTH>', help='(Optional) Specify the month of the data you want to collect.')
    group_main.add_argument('-year', '-y', type=int, metavar='<YEAR>', help='(Optional) Specify the year of the data you want to collect.')

    return parser, parser.parse_args(args)

def check_parse_args(parser):
    if args.year and not args.month: parser.error('-month should be provided when -year is used.')


# ### Animation ######################################### #

class style(str):
    def __init__(self, text):
        style.text = text
    def succeeded(self): return '\033[1;92m' + self.text + '\033[0m'
    def failed(self): return '\033[1;91m' + self.text + '\033[0m'
    def loading(self): return '\033[1;96m' + self.text + '\033[0m'
    def bold(self): return '\033[1m' + self.text + '\033[0m'

class Loader:
    def __init__(self, desc1="Loading...", desc2=" ...", end="Done!", timeout=0.05):
        self.desc1 = desc1
        self.desc2 = desc2
        self.end = end
        self.timeout = timeout

        self._thread = Thread(target=self._animate, daemon=True)
        # self.steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
        self.steps = ["⢎⡰", "⢎⡡", "⢎⡑", "⢎⠱", "⠎⡱", "⢊⡱", "⢌⡱", "⢆⡱"]
        self.done = False

    def start(self):
        self._thread.start()
        return self

    def _animate(self):
        for c in cycle(self.steps):
            status = style(c)
            if self.done:
                break
            print(f"\r{self.desc1} {status.loading()} {self.desc2}", flush=True, end="")
            sleep(self.timeout)

    def __enter__(self):
        self.start()

    def stop(self):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print(f"\r ", flush=True, end='\r')

    def __exit__(self, exc_type, exc_value, tb):
        # handle exceptions with those variables ^
        self.stop()


# ### API Functions ##################################### #

def api_get(f_url, f_verify, f_auth):
    headers['X-Auth-Token'] = '{}'.format(f_auth)
    try:
        f_response = requests.get(url=f_url, headers=headers, verify=f_verify, timeout=300)
        if f_response.status_code != http.client.OK: raise requests.HTTPError(f_response)
        return f_response
    except:
        error_msg = 'TASK   : ' + style('Getting data from the administrator').bold() + ' | STATE:' + style('Failed').failed() + ' | GET: ' +  f_url
        raise Exception(error_msg)

def api_post(f_url, f_verify, f_auth, f_query):
    headers['Authorization'] = 'Basic {}'.format(f_auth)
    try:
        f_response = requests.post(url=f_url, headers=headers, data=f_query, verify=f_verify, timeout=300)
        if f_response.status_code != http.client.OK: raise requests.HTTPError(f_response)
        return f_response
    except:
        error_msg = 'TASK   : ' + style('Getting data from the analyzer').bold() + ' | STATE:' + style('Failed').failed() + ' | GET: ' +  f_url + ' | DATA: ' + f_query
        raise Exception(error_msg)

def generate_session(f_url, f_verify, f_auth):
    headers['Authorization'] = 'Basic {}'.format(f_auth)
    try:
        f_response = requests.post(f_url, headers=headers, verify=f_verify, timeout=300)
        if f_response.status_code != http.client.OK: raise requests.HTTPError(f_response)
        f_token = f_response.headers["X-Auth-Token"]
        return f_token
    except:
        error_msg = 'TASK   : ' + style('Getting token from the administrator').bold() + ' | STATE:' + style('Failed').failed() + ' | POST: ' +  f_url
        raise Exception(error_msg)

def discard_session(f_url, f_verify, f_auth):
    headers['X-Auth-Token'] = '{}'.format(f_auth)
    try:
        f_response = requests.delete(f_url, headers=headers, verify=f_verify, timeout=300)
        if f_response.status_code != http.client.OK: raise requests.HTTPError(f_response)
    except:
        error_msg = 'TASK   : ' + style('Deleting token from the administrator').bold() + ' | STATE:' + style('Failed').failed() + ' | DELETE: ' +  f_url
        print(error_msg)


# ### Helpers ########################################### #

def writeToFile(f_df, f_file):
    if os.path.isfile(f_file):
        f_df.to_csv(f_file, mode='a', sep=' ', header=False, index=False)
    else:
        f_df.to_csv(f_file, sep=' ', header=False, index=False)

def get_auth(f_user, f_password):
    f_up = "{}:{}".format(f_user, f_password)
    f_auth = base64.b64encode(f_up.encode()).decode()
    return f_auth

def get_date():
    today = datetime.today()
    first = today.replace(day=1)
    if not len(sys.argv) > 1:      
        f_edate = first - timedelta(days=1)
        f_edate = f_edate.replace(hour=23).replace(minute=59).replace(second=59)
        f_sdate = f_edate.replace(day=1).replace(hour=00).replace(minute=00).replace(second=00)
    else:
        year = args.year if args.year is not None else datetime.today().strftime('%Y')
        if args.month is not None:
            month = args.month 
        else:
            t_date = first - timedelta(days=1)
            month = t_date.strftime('%m')
        if args.day is not None:
            day = args.day
            f_sdate = str(year) + str(month) + str(day) + ' 000000'
            f_sdate = datetime.strptime(f_sdate, '%Y%m%d %H%M%S')
            f_edate = f_sdate.replace(hour=23).replace(minute=59).replace(second=59)
        else:
            f_sdate = str(year) + str(month) + '01' + ' 000000'
            f_sdate = datetime.strptime(f_sdate, '%Y%m%d %H%M%S')
            next_month = f_sdate.replace(day=28) + timedelta(days=4)
            f_edate = next_month - timedelta(days=next_month.day)
            f_edate = f_edate.replace(hour=23).replace(minute=59).replace(second=59)
    return f_sdate, f_edate

def get_time(f_df, f_item):
    r_df = pd.DataFrame()
    list = f_df['signature'].drop_duplicates().to_list()
    if not 'related.' in str(f_df.columns):
        f_col = f_item + '.start'
    else:
        f_col = 'related.' + f_item + '.start'
    if f_col in f_df.columns:
        f_df = f_df.rename(columns = {f_col:'date'})
    #f_df['date'] = f_df['date'].apply(lambda _: datetime.strptime(_,"%Y%m%d_%H%M%S"))
    f_df['date'] = pd.to_datetime(f_df['date'], format='%Y%m%d_%H%M%S')
    for t_item in list:
        t_df = f_df.loc[f_df['signature'] == t_item].reset_index(drop=True)
        
        if 'related.' in f_col:
            sublist = t_df['related.signature'].drop_duplicates().to_list()
            for u_item in sublist:
                u_df = t_df.loc[t_df['related.signature'] == u_item].reset_index(drop=True)
                u_df['date'] = pd.to_datetime(u_df['date'].astype(str)) + u_df.index * pd.DateOffset(minutes=10)
                r_df = pd.concat([r_df, u_df], ignore_index=True)
        else:
            t_df['date'] = pd.to_datetime(t_df['date'].astype(str)) + t_df.index * pd.DateOffset(minutes=10)
            r_df = pd.concat([r_df, t_df], ignore_index=True)
    r_df['date'] = r_df['date'].dt.strftime('%Y.%m.%d %H:%M:%S')
    return r_df


# ### GET Data ########################################## #

def get_administrator_dataframe(f_data, f_ops):
    global storages
    f_df = pd.DataFrame()
    if not os.path.exists(reportDir): os.makedirs(reportDir)
    task_start = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the administrator "' + f_ops['host'] + '"').bold() + ' | STATE:'
    task_end = '| TARGET: ' + f_ops['host']

    with Loader(task_start, task_end):
        if not storages:
            f_url = f_data['url'].format(f_ops['administratorProtocol'], f_ops['host'], f_ops['administratorPort'])
            f_response = api_get(f_url, f_ops['verify'], token).json()
            f_df = eval("pd.json_normalize({})".format(f_data['jsonfilter']))
            storages = f_df['storageSystemId'].values.tolist()
        else:
            t_df = pd.DataFrame()
            for storage in storages:
                f_url = f_data['url'].format(f_ops['administratorProtocol'], f_ops['host'], f_ops['administratorPort'], storage)
                f_response = api_get(f_url, f_ops['verify'], token).json()
                t_df = eval("pd.json_normalize({})".format(f_data['jsonfilter']))
                if not t_df.empty:
                    t_df['storageSystemId'] = storage
                    f_df = pd.concat([f_df, t_df], ignore_index=True)
        if not f_df.empty:
            for j_item in f_data['data']:
                r_df = pd.DataFrame()
                for k_item in j_item['parameter']['columnsStr']:
                    if k_item == 'date':
                        r_df[k_item] = date
                    else:
                        if k_item in f_df.columns:
                            r_df[k_item] = f_df[k_item]
                        else:
                            r_df[k_item] = None
                    r_df[k_item] = r_df[k_item].astype(str)
                for k_item in j_item['parameter']['columnsFloat']:
                    k = k_item
                    k = k_item.split('InBytes')[0] if 'InBytes' in k_item else k_item
                    k = k_item.split('.')[-2] if '.' in k_item else k_item
                    if k_item in f_df.columns:
                        if '(GB)' in j_item['title']:
                            r_df[k] = f_df[k_item]/1024/1024/1024
                        else:
                            r_df[k] = f_df[k_item]
                    else:
                        r_df[k] = -1
                    r_df[k] = r_df[k].astype(str).str.replace('nan', '-1', regex=True).astype(float)
                if not r_df.empty: 
                    r_file = reportDir + '/' + f_data['table'] + '.' + j_item['id']
                    writeToFile(r_df, r_file)
    
    files = os.listdir(reportDir)
    num_of_items = sum(f_data['table'] in s for s in files)
    if f_df.empty or num_of_items != len(f_data['data']):
        error_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the administrator').bold() + ' | STATE:' + style('Failed').failed() + ' | GET: ' +  f_url
        raise Exception(error_msg)
    else:
        success_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the administrator "' + f_ops['host'] + '"').bold() + ' | STATE:' + style('Succeeded').succeeded()
        print(success_msg)

def get_analyzer_dataframe(f_data, f_ops):
    f_url = f_data['url'].format(f_ops['analyzerProtocol'], f_ops['host'], f_ops['analyzerPort'])
    if not os.path.exists(reportDir): os.makedirs(reportDir)
    task_start = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from analyzer "' + f_ops['host'] + '"').bold() + ' | STATE:'
    task_end = '| TARGET: ' + f_ops['host']

    with Loader(task_start, task_end):
        for j_item in f_data['data']:
            r_df = pd.DataFrame()
            t_edate = sDate
            t_sdate = sDate
            while t_edate != eDate:
                u_df = pd.DataFrame()
                t_edate = (t_sdate + timedelta(days=6)).replace(hour=23).replace(minute=59).replace(second=59)
                if t_edate > eDate:
                    t_edate = eDate
                st_sdate = t_sdate.strftime('%Y%m%d_%H%M%S')
                st_edate = t_edate.strftime('%Y%m%d_%H%M%S')
                query = '{"query":"' + f_data['query'] + '","startTime":"' + st_sdate + '","endTime":"' + st_edate + '"}'
                f_response = api_post(f_url, f_ops['verify'], auth, query).json()
            
                for k_item in j_item['parameter']['columnsFloat']:
                    t_df = pd.DataFrame()
                    if f_data['jsonfilter'].count('{}') == 2:
                        j_filter = f_data['jsonfilter'].format(k_item, k_item)
                    elif f_data['jsonfilter'].count('{}') == 3:
                        j_filter = f_data['jsonfilter'].format(k_item, k_item, k_item)
                    try:
                        f_df = eval("pd.json_normalize({})".format(j_filter))
                        if not f_df.empty:
                            f_df = get_time(f_df, k_item)
                            for s_item in j_item['parameter']['columnsStr']:
                                if s_item == 'storageSystemId':
                                    t_df[s_item] = f_df['signature'].str.split('#').str[1]
                                elif s_item == 'date':
                                    t_df[s_item] = f_df[s_item]
                                else:
                                    t_df[s_item] = f_df['related.signature'].str.split('#').str[1]
                                t_df[s_item] = t_df[s_item].astype(str)
                            t_df[k_item] = f_df['data0']
                            t_df[k_item] = t_df[k_item].astype(float)
                    except:
                        warning_msg = style('!!!').failed() + ' no ' + style(k_item).bold() + ' mql data has been found between ' + style(st_sdate).bold() + ' and ' + style(st_edate).bold()
                        print(warning_msg)

                    if u_df.empty:
                        u_df = t_df
                    else:
                        u_df = u_df.merge(t_df, how = 'outer', on = j_item['parameter']['columnsStr'])

                if not t_df.empty:
                    r_df = pd.concat([r_df, u_df], ignore_index=True)
                t_sdate = (t_edate + timedelta(days=1)).replace(hour=00).replace(minute=00).replace(second=00)

            if not r_df.empty:
                for k_item in j_item['parameter']['columnsFloat']:
                    r_df[k_item] = r_df[k_item].replace(np.nan, -1)
                r_df = r_df.sort_values(by=j_item['parameter']['columnsStr'])
                r_file = reportDir + '/' + f_data['table'] + '.' + j_item['id']
                writeToFile(r_df, r_file)

    files = os.listdir(reportDir)
    num_of_items = sum(f_data['table'] in s for s in files)
    if num_of_items != len(f_data['data']):
        error_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the analyzer').bold() + ' | STATE:' + style('Failed').failed() + ' | GET: ' +  f_url + ' | QUERY: ' + query
        raise Exception(error_msg)
    else:
        success_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the analyzer "' + f_ops['host'] + '"').bold() + ' | STATE:' + style('Succeeded').succeeded()
        print(success_msg)


# ### MAIN Part ######################################### #

if __name__ == "__main__":
    try:
        with open('conf/hvData.json') as dataFile:
            hitachiData = json.load(dataFile)
        dataFile.close()
        with open('conf/hvConf.json') as confFile:
            hitachiConfig = json.load(confFile)
        confFile.close()
    except:
        print(style('!!!').failed() + ' hvData.json or hvConf.json file cannot be opened!')
        raise SystemExit()

    requests.packages.urllib3.disable_warnings()
    warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)
    parser, args = parse_args()
    check_parse_args(parser)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    reportDir = 'hv.' + datetime.today().strftime('%Y%m%d%H%M%S')
    date = datetime.today().strftime('%Y.%m.%d %H:%M:%S')
    sDate, eDate = get_date()

    if len(hitachiConfig['ops']) > 0:
        for ops in hitachiConfig['ops']:
            storages = None
            token_url = "{}://{}:{}/v1/security/tokens".format(ops['administratorProtocol'], ops['host'], ops['administratorPort'])
            auth = get_auth(ops['administratorUser'], ops['administratorPassword'])
            token = generate_session(token_url, ops['verify'], auth)
            if token:
                auth = get_auth(ops['analyzerUser'], ops['analyzerPassword'])
                for singleData in hitachiData:
                    if singleData['type'] == 'administrator':
                        get_administrator_dataframe(singleData, ops)
                    elif singleData['type'] == 'analyzer':
                        get_analyzer_dataframe(singleData, ops)
                discard_session(token_url, ops['verify'], token)
            else:
                error_msg = 'TASK   : ' + style('Getting token from the administrator "' + ops['host'] + '"').bold() + ' | STATE:' + style('Failed').failed() + ' | POST: ' +  token_url
                raise Exception(error_msg)

    num_of_files = len(os.listdir(reportDir))
    if num_of_files > 0:
        shutil.make_archive(reportDir, format='zip', root_dir=reportDir)
    shutil.rmtree(reportDir)
    currentDir = os.getcwd()
    print(style('{}.zip report file created under {} directory.'.format(reportDir, currentDir)).succeeded())
