#!/usr/bin/python

import datetime
import sys


def filter_requests(search_str=None, threshold=1.0, file_path=None):
    if not search_str or not file_path:
        return
    all_reqs = []
    with open(file_path) as f:
        for line in f.readlines():
            if line.find(search_str) > 0:
                parts = line.split(' ')
                time = float(parts[18])
                if time < threshold:
                    continue
                info = {
                    'request_id': parts[5][1:],
                    'tenant_id': parts[7],
                    'user_id': parts[6],
                    'time': time
                }
                all_reqs.append(info)
    return all_reqs


def _get_datetime(date, time):
    date_list = [int(d) for d in date.split('-')]
    time_list = [int(d) for d in time.split('.')[0].split(':')]
    ms = int(time.split('.')[1])
    args = tuple(date_list) + tuple(time_list) + (ms,)
    return datetime.datetime(*args)


def parse_log(logs=[]):
    parsed_logs = []
    start = None
    for log in logs:
        parts = log.split(' ')
        date = parts[0]
        time = parts[1]
        dt = _get_datetime(date, time)
        if not start:
            start = dt
            delta = None
        else:
            delta = dt - start
        parsed_log = {
            'datetime': dt,
            'code': parts[4],
            'req_id': parts[5][1:],
            'tenant_id': parts[7][:-1],
            'user_id': parts[6],
            'delta': delta,
            'content': " ".join(parts[8:])
        }
        parsed_logs.append(parsed_log)
    return parsed_logs


def print_parsed_log(parsed_log):
    delta = parsed_log['delta']
    str_list = []
    if delta:
        str_list.append('+ ' + str(delta))
    else:
        str_list.append(str(parsed_log['datetime']))
    str_list.append(parsed_log['tenant_id'])
    str_list.append(parsed_log['content'])
    print(" ".join(str_list))


def get_logs_by_request_ids(reqs=[], file_path=None):
    if not file_path:
        return
    reqs_set = set(reqs)
    all_logs = {}
    with open(file_path) as f:
        for line in f.readlines():
            line = line.rstrip('\n')
            parts = line.split(' ')
            if len(parts) < 6:
                continue
            req_id = parts[5][1:]
            if req_id in reqs_set:
                if req_id in all_logs:
                    logs = all_logs[req_id]
                else:
                    logs = []
                    all_logs[req_id] = logs
                logs.append(line)
    return all_logs


def test():
    path = '/home/ubuntu/neutron-server.log.2'
    reqs = filter_requests(
        search_str='POST /v2.0/ports', threshold=10, file_path=path)
    req_ids = [req['request_id'] for req in reqs]
    all_logs = get_logs_by_request_ids(req_ids, path)
    for req_id, logs in all_logs.items():
        parsed_logs = parse_log(logs)
        print('====================================')
        print(req_id)
        for parsed_log in parsed_logs:
            print_parsed_log(parsed_log)
        print('====================================\n\n')


def main(search_str, threshold, file_path):
    reqs = filter_requests(search_str, threshold, file_path)
    req_ids = [req['request_id'] for req in reqs]
    all_logs = get_logs_by_request_ids(req_ids, file_path)
    for req_id, logs in all_logs.items():
        parsed_logs = parse_log(logs)
        print('====================================')
        print("API: %s with threshold %s, request_id: %s "
              % (search_str, '>' + str(threshold), req_id))
        for parsed_log in parsed_logs:
            print_parsed_log(parsed_log)
        print('====================================\n\n')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: %s search_string threshold log_file" % sys.argv[0])
        sys.exit(1)
    search_str = sys.argv[1]
    threshold = float(sys.argv[2])
    file_path = sys.argv[3]
    main(search_str, threshold, file_path)
