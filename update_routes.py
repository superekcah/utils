#!/usr/bin/python

import os
from netaddr import IPNetwork
from neutronclient.v2_0 import client as clientv20

client = None
public_service_cidrs = '10.180.8.0/22'
vpn_cidr = '10.180.66.0/23'
private_gateway = '10.180.64.1'


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


def check_idc_net(client, net):
    subnets = net.get('subnets', [])
    if not subnets:
        print('%s has no subnet' % net['id'])
        return ([], [])
    subnet_id = subnets[0]
    subnet = client.show_subnet(subnet_id)['subnet']
    if not subnet:
        print('%s has no subnet' % net['id'])
        return ([], [])
    host_routes = subnet['host_routes']
    link_route = None
    private_ip_routes = []
    public_services_routes = []
    new_routes = []
    need_update = False
    gateway = None
    for route in host_routes:
        nexthop = route['nexthop']
        destination = route['destination']
        if nexthop == '0.0.0.0':
            link_route = route
            gateway = str(IPNetwork(destination).ip + 1)
        elif destination in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']:
            private_ip_routes.append(route)
        else:
            public_services_routes.append(route)
    if not link_route:
        print('subnet %s has no link scope route' % subnet_id)
        return ([], [])
    new_routes.append(link_route)
    if len(private_ip_routes) != 3:
        print('%s private ips routes are incorrect' % net['id'])
        need_update = True
    new_routes.extend([
        {'destination': '10.0.0.0/8', 'nexthop': gateway, 'order': 10},
        {'destination': '172.16.0.0/12', 'nexthop': gateway, 'order': 10},
        {'destination': '192.168.0.0/16', 'nexthop': gateway, 'order': 10}
    ])
    pub_cidrs = []
    for cidr in public_service_cidrs.split(','):
        pn = IPNetwork(cidr)
        pub_cidrs.extend([str(c) for c in pn.subnet(pn.prefixlen + 1)])
    new_pub_routes = [{'destination': c, 'nexthop': gateway, 'order': 10}
                      for c in pub_cidrs]
    if (set([r['destination'] for r in new_pub_routes])
            != set([r['destination'] for r in public_services_routes])):
        need_update = True
    new_routes.extend(new_pub_routes)
    return (new_routes, host_routes) if need_update else ([], host_routes)


def check_private_net(client, net):
    subnets = net.get('subnets', [])
    if not subnets:
        print('%s has no subnet' % net['id'])
        return ([], [])
    subnet_id = subnets[0]
    subnet = client.show_subnet(subnet_id)['subnet']
    if not subnet:
        print('%s has no subnet' % net['id'])
        return ([], [])
    host_routes = subnet['host_routes']
    dests = [route['destination'] for route in host_routes]
    new_dsts = ['169.254.169.254/32', vpn_cidr]
    new_dsts.extend([c for c in public_service_cidrs.split(',')])
    if set(new_dsts) == set(dests):
        return ([], host_routes)
    new_routes = [{'destination': d, 'nexthop': private_gateway, 'order': 10}
                  for d in new_dsts]
    return (new_routes, host_routes)


def check_networks():
    neutron = get_client()
    networks = neutron.list_networks().get('networks')
    idc_nets = {}
    private_nets = {}
    for net in networks:
        net_name = net.get('name')
        if not net_name:
            continue
        if net_name.startswith('idc_'):
            new_routes, old_routes = check_idc_net(client, net)
            if new_routes:
                idc_nets[net['id']] = (net, new_routes, old_routes)
        elif net_name.startswith('private_'):
            new_routes, old_routes = check_private_net(client, net)
            if new_routes:
                private_nets[net['id']] = (net, new_routes, old_routes)
    return (idc_nets, private_nets)


def update_subnet_routes_str(subnet_id, routes):
    rt_str = ''
    for rt in routes:
        rt_str += (' destination=%s,nexthop=%s,order=%s '
                   % (rt['destination'], rt['nexthop'], rt['order']))
    cmd = ('neutron subnet-update %s --host_routes list=true type=dict %s'
           % (subnet_id, rt_str))
    return cmd


def dump_update_script(idc_nets, private_nets):
    content = '#!/bin/bash\n\n'

    content += '# IDC networks #\n\n'
    for net, new_routes, old_routes in idc_nets.itervalues():
        net_name = net['name']
        subnet_id = net['subnets'][0]
        content += '# %s old routes: %s\n' % (net_name, str(old_routes))
        content += update_subnet_routes_str(subnet_id, new_routes) + '\n\n'

    content += '# Private networks #\n\n'
    for net, new_routes, old_routes in private_nets.itervalues():
        net_name = net['name']
        subnet_id = net['subnets'][0]
        content += '# %s old routes: %s\n' % (net_name, str(old_routes))
        content += update_subnet_routes_str(subnet_id, new_routes) + '\n\n'

    return content


def main():
    idc_nets, private_nets = check_networks()
    content = dump_update_script(idc_nets, private_nets)
    path = './update.sh'
    with open(path, 'w') as f:
        f.write(content)


if __name__ == '__main__':
    main()
