#!/usr/bin/python

import collections
import os
import sys
import uuid

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


def _get_agents(agent_type=None):
    q_client = get_client()
    if agent_type:
        search_opts = {'agent_type': agent_type}
        return q_client.list_agents(**search_opts)['agents']
    else:
        return q_client.list_agents()['agents']


def get_l3_agents():
    return _get_agents(agent_type='L3 agent')


def get_dhcp_agents():
    return _get_agents(agent_type='DHCP agent')


def get_ovs_agents():
    return _get_agents(agent_type='Open vSwitch agent')


class RouterChecker(object):
    def __init__(self):
        self.q_client = get_client()
        self.non_ha_routers = set()
        self.spf_routers = set()
        self.unbound_routers = set()
        self.duplicated_routers = set()
        self.ha_state_failed_routers = set()
        self.normal_routers = set()
        self.agent_routers_mapping = {}
        self.routers = None
        self.router_ports_mapping = collections.defaultdict(list)
        self.deprecated_ports = set()
        self.agent_needs_remove = collections.defaultdict(list)

    def get_all_routers(self):
        routers = self.q_client.list_routers()['routers']
        self.routers = routers
        skipped_routers = []
        while routers:
            for router in routers:
                try:
                    self._get_router_port(router)
                except Exception:
                    skipped_routers.append(router)
            if skipped_routers:
                routers = skipped_routers
                skipped_routers = []
            else:
                routers = None

    def _get_router_port(self, router):
        router_id = router['id']
        if not router['is_ha'] or router['ha_type'] != 'keepalived':
            self.non_ha_routers.add(router_id)
            return
        router_ports =\
            self.q_client.router_port_list(router['id'])['ports']
        self.router_ports_mapping[router_id] = router_ports
        if not router_ports or len(router_ports) == 1:
            self.unbound_routers.add(router_id)
            return
        if len(router_ports) == 2:
            self.spf_routers.add(router_id)
        if len(router_ports) > 3:
            self.duplicated_routers.add(router_id)
        # router bind to two agents
        vip_port = None
        master_port = None
        backup_port = None
        non_exist_agent = 0
        for port in router_ports:
            if not port['l3_agent_id']:
                if not vip_port:
                    # gateway vip
                    vip_port = port
                    continue
                else:
                    # agent had been deleted?
                    self.deprecated_ports.add(port['id'])
                    non_exist_agent += 1
                    continue
            else:
                agent_id = port['l3_agent_id']
                if agent_id not in self.agent_routers_mapping:
                    self.agent_routers_mapping[agent_id] =\
                        collections.defaultdict(list)

            if port['status'] == 'MASTER' and not master_port:
                master_port = port
                self.normal_routers.add(router_id)
                self.agent_routers_mapping[agent_id]['MASTER'].append(
                    router_id)
            elif port['status'] == 'BACKUP' and not backup_port:
                backup_port = port
                self.normal_routers.add(router_id)
                self.agent_routers_mapping[agent_id]['BACKUP'].append(
                    router_id)
            elif (port['status'] == 'BACKUP'
                    and router_id in self.duplicated_routers):
                self.agent_needs_remove[port['l3_agent_id']].append(router_id)
            else:
                # fault, or multiple master, or multiple backup
                self.ha_state_failed_routers.add(router_id)
                self.agent_routers_mapping[agent_id]['FAULT'].append(
                    router_id)
        valid_ports = len(router_ports) - non_exist_agent
        if valid_ports == 2:
            self.spf_routers.add(router_id)
        elif valid_ports == 1:
            self.unbound_routers.add(router_id)

    def check_routers_state(self):
        all_l3_agents = get_l3_agents()
        for agent in all_l3_agents:
            if agent['id'] not in self.agent_routers_mapping:
                self.agent_routers_mapping[agent['id']] =\
                    collections.defaultdict(list)
        for agent_id, routers in self.agent_routers_mapping.items():
            master_routers = routers['MASTER']
            backup_routers = routers['BACKUP']
            fault_routers = routers['FAULT']
            total =\
                len(master_routers) + len(backup_routers) + len(fault_routers)
            print("\nL3 Agent %s have %d routers: %d master %d backup %d fault"
                  % (agent_id, total, len(master_routers), len(backup_routers),
                     len(fault_routers)))
            if master_routers:
                print('Master:')
                print('\n'.join(master_routers))
            if backup_routers:
                print('Backup:')
                print('\n'.join(backup_routers))
            if fault_routers:
                print('Fault:')
                print('\n'.join(fault_routers))
        print("\nTotal %d routers, %d is no HA, %d not bound, %d bind to one "
              "agent, %d bind to more than two agents, %d HA status abnormal"
              % (len(self.routers), len(self.non_ha_routers),
                 len(self.unbound_routers), len(self.spf_routers),
                 len(self.duplicated_routers),
                 len(self.ha_state_failed_routers)))
        if self.non_ha_routers:
            print("\nRouter is not HA:")
            print('\n'.join(self.non_ha_routers))
        if self.unbound_routers:
            print("\nRouter not bound:")
            print('\n'.join(self.unbound_routers))
        if self.spf_routers:
            print("\nRouter bind to only one agent:")
            print('\n'.join(self.spf_routers))
        if self.duplicated_routers:
            print("\nRouter bind to more than two agent:")
            print('\n'.join(self.duplicated_routers))
        if self.ha_state_failed_routers:
            print("\nRouter's HA state abnormal")
            print("\n".join(self.ha_state_failed_routers))

        if self.deprecated_ports:
            print("\nL3 Agents have been deleted, port deprecated:")
            print('\n'.join(self.deprecated_ports))

    def get_l3_binding_db(self, router_id):
        return self.q_client.list_l3_agent_hosting_routers(router_id)['agents']

    def _get_actual_agents_from_ports(self, router_id):
        ports = self.router_ports_mapping[router_id]
        actual_agent_ids = set()
        for port in ports:
            if port['l3_agent_id']:
                actual_agent_ids.add(port['l3_agent_id'])
        return actual_agent_ids

    def recover_ha(self, dump=False):
        if not self.spf_routers and not self.unbound_routers:
            return
        ret_mapping = collections.defaultdict(set)
        td_routers = self.unbound_routers | self.spf_routers
        skipped_routers = set()
        while td_routers:
            for router_id in td_routers:
                agents = None
                try:
                    agents = self.get_l3_binding_db(router_id)
                    db_agent_ids = set([agt['id'] for agt in agents])
                    actual_agent_ids = self._get_actual_agents_from_ports(
                        router_id)
                    need_add = db_agent_ids - actual_agent_ids
                    for agent_id in need_add:
                        ret_mapping[agent_id].add(router_id)
                except Exception:
                    skipped_routers.add(router_id)
                    continue
            td_routers = skipped_routers
            skipped_routers = set()
        if dump:
            for agent_id, routers in ret_mapping.items():
                for router_id in routers:
                    print('neutron l3-agent-router-add %s %s'
                          % (agent_id, router_id))
        return ret_mapping

    def _get_least_used_agents(self, agents_usages):
        tmp = [(k, v) for (k, v) in agents_usages.iteritems()]
        agents = sorted(tmp, key=lambda x: x[1])
        return [i[0] for i in agents]

    def reschedule_routers(self, exclude_l3_agents=None, dump=False):
        agent_to_remove_router = collections.defaultdict(list)
        agent_to_add_router = collections.defaultdict(list)
        current_agent_routers = {}
        agent_counts = {}
        all_l3_agents = get_l3_agents()
        if exclude_l3_agents:
            # ignore excluded l3 agents
            all_l3_agents = [agt for agt in all_l3_agents
                             if agt['id'] not in exclude_l3_agents]
            for agent_id in exclude_l3_agents:
                self.agent_routers_mapping.pop(agent_id, None)
        # distribute routers to l3 agents equally
        router_per_agent =\
            len(self.routers) * 2 / len(all_l3_agents)
        for agent_id, routers in self.agent_routers_mapping.items():
            master = 0
            backup = 0
            fault = 0
            backup_routers = []
            master_routers = []
            for state, router_list in routers.items():
                if state == 'MASTER':
                    master = len(router_list)
                    master_routers = router_list
                elif state == 'BACKUP':
                    backup = len(router_list)
                    backup_routers = router_list
                else:
                    fault = len(router_list)
                    if fault > 0:
                        agent_to_remove_router[agent_id].extend(router_list)
            # routers should be removed
            num_to_migrate = master + backup - router_per_agent
            if agent_id in self.agent_needs_remove:
                num_to_migrate -= len(set(self.agent_needs_remove[agent_id]))
            if num_to_migrate > 0:
                # remove backup first
                if num_to_migrate <= backup:
                    agent_to_remove_router[agent_id].extend(
                        backup_routers[:num_to_migrate])
                    backup_routers = backup_routers[num_to_migrate:]
                    backup -= num_to_migrate
                else:
                    agent_to_remove_router[agent_id].extend(backup_routers)
                    agent_to_remove_router[agent_id].extend(
                        master_routers[:(num_to_migrate - backup)])
                    backup_routers = []
                    master_routers = master_routers[(num_to_migrate - backup):]
                    master -= num_to_migrate - backup
                    backup = 0
            current_agent_routers[agent_id] =\
                set(master_routers) | set(backup_routers)
            agent_counts[agent_id] = {
                'master': master,
                'backup': backup,
                'num_to_migrate': num_to_migrate,
            }
        # empty l3 agent
        for agt in all_l3_agents:
            if agt['id'] not in agent_counts:
                agent_counts[agt['id']] = {
                    'master': 0,
                    'backup': 0,
                    'num_to_migrate': (0 - router_per_agent)
                }
                current_agent_routers[agt['id']] = set()
        # bind spf router to another l3 agent
        routers_to_add = list(self.spf_routers)
        # bind all removed routers back
        for agent_id, routers in agent_to_remove_router.items():
            routers_to_add.extend(routers)
            agent_to_remove_router[agent_id].extend(
                self.agent_needs_remove[agent_id])
        for agent_id, counts in agent_counts.items():
            if counts['num_to_migrate'] < 0:
                num_to_add = 0 - counts['num_to_migrate']
                index = 0
                while num_to_add > 0 and len(routers_to_add) > index:
                    router_id = routers_to_add[index]
                    if (router_id in agent_to_add_router[agent_id]
                            or router_id in current_agent_routers[agent_id]):
                        index += 1
                    else:
                        num_to_add -= 1
                        agent_to_add_router[agent_id].append(router_id)
                        del routers_to_add[index]
        agent_usages = {}
        for agent_id in agent_counts.keys():
            agent_usages[agent_id] =\
                len(agent_to_add_router[agent_id]) +\
                len(current_agent_routers[agent_id])
        if len(routers_to_add) > 0:
            for router_id in routers_to_add:
                sorted_agents = self._get_least_used_agents(agent_usages)
                for agt_id in sorted_agents:
                    if not (router_id in agent_to_add_router[agt_id]
                            or router_id in current_agent_routers[agt_id]):
                        agent_to_add_router[agt_id].append(router_id)
                        agent_usages[agt_id] = agent_usages[agt_id] + 1
                        break
        if self.unbound_routers:
            for router_id in self.unbound_routers:
                sorted_agents = self._get_least_used_agents(agent_usages)
                for i in [0, 1]:
                    for agt_id in sorted_agents:
                        if not (router_id in agent_to_add_router[agt_id]
                                or router_id in current_agent_routers[agt_id]):
                            agent_to_add_router[agt_id].append(router_id)
                            agent_usages[agt_id] = agent_usages[agt_id] + 1
                            break
        if dump:
            for agent_id, routers in agent_to_remove_router.items():
                if routers:
                    print("\nAgent %s need to remove routers" % agent_id)
                    print('\n'.join(set(routers)))
            for agent_id, routers in agent_to_add_router.items():
                if routers:
                    print("\nAgent %s need to add routers" % agent_id)
                    print('\n'.join(set(routers)))
        return (agent_to_add_router, agent_to_remove_router)


def help():
    doc = """
program command

command:
    router-check
    recover-ha
    router-reschedule [exclude-l3-agent-uuid-list]
    router-reschedule-script [exclude-l3-agent-uuid-list]
    """
    print(doc)


def _is_uuid(val):
    try:
        return str(uuid.UUID(val)) == val
    except Exception:
        return False


def main(argv):
    if len(argv) < 2:
        help()
        return

    command = argv[1]
    exclude_l3_agents = []
    if command == 'router-check':
        router_checker = RouterChecker()
        router_checker.get_all_routers()
        router_checker.check_routers_state()
    elif command == 'recover-ha':
        router_checker = RouterChecker()
        router_checker.get_all_routers()
        router_checker.recover_ha(dump=True)
    elif command == 'router-reschedule':
        if len(argv) > 2:
            for id_str in argv[2:]:
                if _is_uuid(id_str):
                    exclude_l3_agents.append(id_str)
                else:
                    help()
                    return
        router_checker = RouterChecker()
        router_checker.get_all_routers()
        router_checker.reschedule_routers(exclude_l3_agents=exclude_l3_agents,
                                          dump=True)
    elif command == 'router-reschedule-script':
        if len(argv) > 2:
            for id_str in argv[2:]:
                if _is_uuid(id_str):
                    exclude_l3_agents.append(id_str)
                else:
                    help()
                    return
        router_checker = RouterChecker()
        router_checker.get_all_routers()
        agent_to_add, agent_to_remove = router_checker.reschedule_routers(
            exclude_l3_agents=exclude_l3_agents)
        print("\n# Remove routers from agent")
        for agent_id, routers in agent_to_remove.items():
            for router in routers:
                print("neutron l3-agent-router-remove %s %s"
                      % (agent_id, router))
        print("\n# Add routers to agent")
        for agent_id, routers in agent_to_add.items():
            for router in routers:
                print("neutron l3-agent-router-add %s %s"
                      % (agent_id, router))
    else:
        help()


if __name__ == '__main__':
    main(sys.argv)
