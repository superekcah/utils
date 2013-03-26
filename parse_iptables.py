#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import subprocess


cur_table = None
all_chains = {}
top_chains = {}
tables = {}

class Chain(object):
    def __init__(self, name, table, policy, packet, byte):
        self.name = name
        self.table = table
        self.policy = policy
        self.packet = int(packet)
        self.byte = int(byte)
        self.rules = []

    def __repr__(self):
        return "%s(%s)" % (self.__class__, self.name)

    def __str__(self):
        return "%s %s [%d:%d]" % (self.name, self.policy, self.packet, self.byte)

    def add_rule(self, cond, target, pkt, byte):
        self.rules.append((cond, target, pkt, byte))

    def pretty_print(self, indent=''):
        for cond, target, pkt, byte in self.rules:
            if isinstance(target, Chain):
                print(indent + "-A %s %s -j %s\t[%d:%d]" 
                        % (self.name, cond, target.name, pkt, byte))
                target.pretty_print(indent + '  ')
            else:
                print(indent + "-A %s %s -j %s\t[%d:%d]" % (self.name, cond, target, pkt, byte))

def parse_line(line):
    if not line:
        return
    c = line[0:1]
    if c == '#':
        # comment
        pass
    elif c == '*':
        # table
        global cur_table
        cur_table = line[1:].strip()
    elif c == ':':
        # chain
        parts = line[1:].split()
        chain = parts[0]
        policy = parts[1]
        counts = parts[2][1:-1].split(':')
        chain_obj = Chain(**{'name':chain, 'policy':policy, 'table':cur_table,
                'packet':counts[0], 'byte':counts[1]})
        key = cur_table + ":" + chain
        all_chains[key] = chain_obj
        top_chains[key] = chain_obj
        
    elif c == '[':
        # rules
        parts = line.split()
        counts = parts[0][1:-1].split(':')
        chain_name = parts[2]
        key = cur_table + ":" + chain_name
        if key not in all_chains:
            print("Error: unknown chain %s" % chain_name)
            return
        chain = all_chains[key]
        remain_parts = ' '.join(parts[3:]).split('-j')
        cond = remain_parts[0].strip()
        target = remain_parts[1].strip()

        if target.split()[0] in ['SNAT', 'DNAT', 'ACCEPT', 'DROP', 
                'MASQUERADE', 'CHECKSUM', 'QUEUE', 'MARK', 'RETURN']:
            chain.add_rule(cond, target, int(counts[0]), int(counts[1]))
        else:
            key = cur_table + ":" + target.split()[0]
            chain.add_rule(cond, all_chains[key], int(counts[0]), int(counts[1]))
            if key in top_chains:
                del top_chains[key]

def group_results():
    for key in top_chains:
        tbl = key.split(":")[0]
        if tbl in tables:
            tables[tbl].append(top_chains[key])
        else:
            tables[tbl] = [top_chains[key]]


if __name__ == '__main__':
    if len(sys.argv) == 2:
        with open(sys.argv[1]) as f:
            for line in f.readlines():
                parse_line(line)
    else:
        popen = subprocess.Popen("sudo iptables-save -c", 
                    shell=True, stdout=subprocess.PIPE)
        content = popen.stdout.readlines()
        for line in content:
            parse_line(line)
    group_results()
    for tbl in tables:
        print("-t %s" % tbl)
        for chain in tables[tbl]:
            print("%s\t[%d:%d]" % (chain.name, chain.packet, chain.byte))
            chain.pretty_print('  ')
        print('')
