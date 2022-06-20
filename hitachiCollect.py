#!/usr/bin/python3
# -*- coding: latin-1 -*-

# COPYRIGHT
# © 2022 Hitachi Vantara LLC. All rights reserved.

import requests
import json
import time
import os, sys, re
import base64
import http.client
import argparse
import pandas as pd
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
'''.format(prog="hitachiCollect")

def parse_args(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(prog="hitachiCollect", description='Use the ' + "hitachiCollect" + ' command to collect data for reporting.', epilog=examples, formatter_class=argparse.RawDescriptionHelpFormatter, add_help=False)

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

def api_get(f_type, f_url, f_verify, f_auth, f_query=None):
    if f_type == 'administrator':
        headers['X-Auth-Token'] = '{}'.format(f_auth)
    elif f_type == 'analyzer':
        headers['Authorization'] = 'Basic {}'.format(f_auth)

    try:
        if not f_query:
            f_response = requests.get(url=f_url, headers=headers, verify=f_verify, timeout=300)
        else:
            f_response = requests.get(url=f_url, headers=headers, data=f_query, verify=f_verify, timeout=300)
        if f_response.status_code != http.client.OK: raise requests.HTTPError(f_response)
        return f_response
    except:
        error_msg = 'TASK   : ' + style('Getting data from the ' + f_type).bold() + ' | STATE:' + style('Failed').failed() + ' | GET: ' +  f_url + ' | DATA: ' + f_query
        raise Exception(error_msg)

def generate_session(f_url, f_verify, f_auth):
    headers['Authorization'] = 'Basic {}'.format(f_auth)
    try:
        f_response = requests.post(f_url, headers=headers, verify=f_verify, timeout=300)
        if f_response.status_code != http.client.OK: raise requests.HTTPError(f_response)
        f_token = f_response.headers.json()["X-Auth-Token"]
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

def get_auth(f_ops):
    f_up = "{}:{}".format(f_ops['user'], f_ops['password'])
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
            f_sdate = year + month + day + ' 000000'
            f_edate = year + month + day + ' 235959'
        else:
            f_sdate = year + month + '01' + ' 000000'
            f_sdate = datetime.strptime(f_sdate, '%Y%m%d %H%M%S')
            next_month = f_sdate.replace(day=28) + timedelta(days=4)
            f_edate = next_month - timedelta(days=next_month.day)
            f_edate = f_edate.replace(hour=23).replace(minute=59).replace(second=59)
    return f_sdate, f_edate

def get_time(f_sdate, f_edate, f_len):
    dict = []
    t_df = pd.DataFrame()
    while f_sdate < f_edate:
        dict.append(f_sdate.strftime('%Y.%m.%d %H:%M:%S'))
        f_sdate += timedelta(minutes=10)
    t_df['date'] = dict
    n = int(f_len/len(t_df))
    pd.concat([t_df]*n, ignore_index=True)
    return t_df


# ### GET Data ########################################## #

def get_administrator_dataframe(f_data, f_ops):
    f_url = f_data['url'].format(f_ops['protocol'], f_ops['host'], f_ops['port'])
    if token:
        r_df = pd.DataFrame()
        if not os.path.exists(reportDir): os.makedirs(reportDir)
        task_start = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the administrator').bold() + ' | STATE:'
        task_end = '| TARGET: ' + f_ops['host']

        with Loader(task_start, task_end):
            f_response = api_get('administrator', f_url, f_ops['verify'], token).json()
            f_df = eval("pd.json_normalize({})".format(f_data['jsonfilter']))
            if not f_df.empty:
                for j_item in f_data['data']:
                    for k_item in j_item['parameter']['columnsStr']:
                        if k_item == 'date':
                            r_df[k_item] = date
                        else:
                            r_df[k_item] = f_df[k_item]
                        r_df[k_item] = r_df[k_item].astype(str)
                    for k_item in j_item['parameter']['columnsFloat']:
                        k = k_item
                        k = k_item.split('InBytes')[0] if 'InBytes' in k_item else k_item
                        k = k_item.split('.')[-2] if '.' in k_item else k_item
                        if '(GB)' in j_item['title']:
                            r_df[k] = f_df[k_item]/1024/1024/1024
                        else:
                            r_df[k] = f_df[k_item]
                        r_df[k] = r_df[k].astype(float)
                    if not r_df.empty: r_df.to_csv(reportDir + '/' + f_data['table'] + '.' + j_item['id'], sep=' ', header=False, index=False)
        
        files = os.listdir(reportDir)
        num_of_items = sum(f_data['table'] in s for s in files)
        if f_df.empty or num_of_items != len(f_data['data']):
            error_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the administrator').bold() + ' | STATE:' + style('Failed').failed() + ' | GET: ' +  f_url
            raise Exception(error_msg)
        else:
            success_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the administrator').bold() + ' | STATE:' + style('Succeeded').succeeded()
            print(success_msg)
    else:
        error_msg = 'TASK   : ' + style('Getting token from the administrator').bold() + ' | STATE:' + style('Failed').failed() + ' | POST: ' +  token_url
        raise Exception(error_msg)

def get_analyzer_dataframe(f_data, f_ops):
    f_url = f_data['url'].format(f_ops['protocol'], f_ops['host'], f_ops['port'])
    if not os.path.exists(reportDir): os.makedirs(reportDir)
    task_start = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from analyzer').bold() + ' | STATE:'
    task_end = '| TARGET: ' + f_ops['host']

    with Loader(task_start, task_end):
        for j_item in f_data['data']:
            r_df = pd.DataFrame()
            t_edate = sDate
            t_sdate = sDate
            while t_edate != eDate:
                t_edate = (t_sdate + timedelta(days=6)).replace(hour=23).replace(minute=59).replace(second=59)
                if t_edate > eDate:
                    t_edate = eDate
                st_sdate = t_sdate.strftime('%Y%m%d_%H%M%S')
                st_edate = t_edate.strftime('%Y%m%d_%H%M%S')
                tf_df = pd.DataFrame()
                ts_df = pd.DataFrame()
                query = '{"query":"({}}","startTime":"{}}","endTime":"{}}"}'.format(f_data['query'], st_sdate, st_edate)
                f_response = api_get('analyzer', f_url, f_ops['verify'], query, auth).json()
            
                for k_item in j_item['parameter']['columnsFloat']:
                    if f_data['jsonfilter'].count('{}') == 1:
                        j_filter = f_data['jsonfilter'].format(k_item)
                    elif f_data['jsonfilter'].count('{}') == 2:
                        j_filter = f_data['jsonfilter'].format(k_item, k_item)
                    f_df = eval("pd.json_normalize({})".format(j_filter))
                    if not f_df.empty:
                        tf_df[k_item] = f_df['data0']
                        tf_df[k_item] = tf_df[k_item].astype(float)
                if not f_df.empty:
                    for k_item in j_item['parameter']['columnsStr']:
                        if k_item == 'storageSystemId':
                            ts_df[k_item] = f_df['signature'].str.split('#').str[1]
                        elif k_item == 'date':
                            ts_df[k_item] = (pd.DataFrame(t_sdate, t_edate, len(f_df)))['date']
                        else:
                            ts_df[k_item] = f_df['related.signature'].str.split('#').str[1]
                            ts_df[k_item] = ts_df[k_item].astype(str)
                if not ts_df.empty:
                    ts_df = ts_df.join(tf_df)
                    r_df = pd.concat([r_df, ts_df], ignore_index=True)
                t_sdate = (t_edate + timedelta(days=1)).replace(hour=00).replace(minute=00).replace(second=00)

            if not r_df.empty:
                dict = j_item['parameter']['columnsStr']
                dict.remove('date')
                r_df = r_df.sort_values(by=dict)
                r_df.to_csv(reportDir + '/' + f_data['table'] + '.' + j_item['id'], sep=' ', header=False, index=False)

    files = os.listdir(reportDir)
    num_of_items = sum(f_data['table'] in s for s in files)
    if num_of_items != len(f_data['data']):
        error_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the analyzer').bold() + ' | STATE:' + style('Failed').failed() + ' | GET: ' +  f_url
        raise Exception(error_msg)
    else:
        success_msg = 'TASK   : ' + style('Getting "' + f_data['title'] + '" information from the analyzer').bold() + ' | STATE:' + style('Succeeded').succeeded()
        print(success_msg)


# ### MAIN Part ######################################### #

if __name__ == "__main__":
    try:
        with open('conf/hitachiData.json') as dataFile:
            hitachiData = json.load(dataFile)
        with open('conf/hitachiConf.json') as confFile:
            hitachiConfig = json.load(confFile)
    except:
        print(style('!!!').failed() + ' hitachiData.json or hitachiConf.json file cannot be opened!')
        raise SystemExit()

    requests.packages.urllib3.disable_warnings()
    parser, args = parse_args()
    check_parse_args(parser)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    reportDir = 'hv.' + datetime.today().strftime('%Y%m%d%H%M%S')
    date = datetime.today().strftime('%Y.%m.%d %H:%M:%S')
    sDate, eDate = get_date()

    if len(hitachiConfig['administrator']) > 0:
        for ops in hitachiConfig['administrator']:
            token_url = "{}://{}:{}/v1/security/tokens".format(ops['protocol'], ops['host'], ops['port'])
            auth = get_auth(ops)
            token = generate_session(token_url, ops['verify'], auth)
            for singleData in hitachiData:
                if singleData['type'] == 'administrator':
                    get_administrator_dataframe(singleData, ops)
            discard_session(token_url, ops['verify'], auth)

    if len(hitachiConfig['analyzer']) > 0:
        for ops in hitachiConfig['analyzer']:
            auth = get_auth(ops)
            for singleData in hitachiData:
                if singleData['type'] == 'analyzer':
                    get_analyzer_dataframe(singleData, ops)
