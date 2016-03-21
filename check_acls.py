#!/usr/bin/python

import math
import netaddr
import os
import sys

from neutronclient.v2_0 import client as clientv20


client = None


def get_client():
    global client
    if client:
        return client
    params = {}
    params['username'] = os.environ.get('OS_USERNAME')
    params['password'] = os.environ.get('OS_PASSWORD')
    params['tenant_name'] = os.environ.get('OS_TENANT_NAME')
    params['auth_url'] = os.environ.get('OS_AUTH_URL')
    params['region_name'] = os.environ.get('OS_REGION_NAME')
    client = clientv20.Client(**params)
    return client


def _convert_to_cidr(first, last):
    num = math.log((last - first + 1), 2)
    num_int = int(num)
    _first = -1
    _last = -1
    if num_int != num:
        tmp = first + int(math.pow(2, num_int)) - 1
        _last = last
        last = tmp
        _first = tmp + 1
    prelen = 32 - num_int
    ip = netaddr.IPAddress(first)
    cidr = str(ip) + '/' + str(prelen)
    if _first > 0 and _last > 0:
        cidr += ',' + _convert_to_cidr(_first, _last)
    return cidr


def check_cidrs(cidrs):
    def _compare_cidr(c1, c2):
        if c1[0] != c2[0]:
            return c1[0] - c2[0]
        else:
            return c2[1] - c1[1]

    tmp_list = []
    for c in cidrs:
        net = netaddr.IPNetwork(c)
        tmp_list.append((net.first, net.last))
    cidr_list = sorted(tmp_list, cmp=_compare_cidr)
    cur_first = -2
    cur_last = -2
    effective_cidr = []
    overlapped_cidr = []
    for first, last in cidr_list:
        if (cur_last + 1) < first:
            if cur_first <= cur_last and cur_first > 0:
                effective_cidr.append((cur_first, cur_last))
            cur_first = first
            cur_last = last
        elif (cur_last + 1) == first:
            # continuous
            cur_last = last
        else:  # overlapped
            if cur_last < last:
                _last = cur_last
                cur_last = last
            else:
                _last = last
            overlapped_cidr.append((first, _last))
    if cur_last >= cur_first and cur_first >= 0:
        effective_cidr.append((cur_first, cur_last))
    print("setted acls: %s" % ','.join([_convert_to_cidr(first, last)
                                       for first, last in cidr_list]))
    if cidr_list != effective_cidr:
        print('effective acls: %s'
              % ','.join([_convert_to_cidr(first, last)
                         for first, last in effective_cidr]))
    if overlapped_cidr:
        print('overlapped cidrs: %s'
              % ','.join([_convert_to_cidr(first, last)
                         for first, last in overlapped_cidr]))


def check_tenant_acls(tenant_id):
    neutron = get_client()
    search_opts = {'tenant_id': tenant_id}
    acls = neutron.list_accesslists(**search_opts).get('accesslists')
    if not acls:
        return
    cidrs = set([acl['destination'] for acl in acls])
    check_cidrs(cidrs)


def check_tenants(list_file):
    with open(list_file) as f:
        for tenant in f.readlines():
            tenant = tenant.rstrip('\n')
            print("tenant %s" % tenant)
            check_tenant_acls(tenant)
            print('\n')


def test_cidrs():
    cidrs = ["10.110.92.0/24", "10.120.103.0/24", "10.120.104.0/24",
             "10.120.105.0/24", "10.120.144.0/20", "10.140.2.0/24",
             "10.160.128.0/24", "10.160.215.0/24", "10.160.247.0/24",
             "10.165.136.0/28", "10.165.149.131/32", "172.17.0.0/20"]
    check_cidrs(cidrs)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usege: check_acls.py tenant_list")
        sys.exit(1)
    tenant_list = sys.argv[1]
    check_tenants(tenant_list)
#    test_cidrs()
