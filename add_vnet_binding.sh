#!/bin/bash

ALL_TENANTS="$(keystone tenant-list | grep Project | awk '{print $2}')"
AZ='yz'
NETWORK_ID='961fcd33-34b6-440e-b1f8-1c431f0e0691'
VNET='public'

for t in $ALL_TENANTS
do
    echo "neutron vnet-binding-create --az $AZ --network $NETWORK_ID --tenant-id $t --vnet $VNET" >> add_${AZ}.sh
done
