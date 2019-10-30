# Pelagos howto

Pelagios is artless pxe boot and provisioning system which created especially
for connecting bare metal nodes to ceph/teuthology testing system

It based on ideas:
  
* boot images should ready for boot, if you need provisioning use kiwi oem images

* boot process could be controlled and observed via REST interfaces

* target node are controlled via ipmi

* conman is used for collecting node consoles output

* by default, system is using dnsmasq as dhcp/dns service and generate configuration files for it.

## Installation environment preparation

### Setup needed packages

Install on both target and admin/development host in virtual env.
Probably disto packages could be used.

    pip install salt flask pytest jsonify

### Prepare salt env

Copy salt master file and correct it

    cp master.sample master

### Configure ssh password-less access

in `~/.ssh/config` add

    Host a.b.c.d
            User root
            StrictHostKeyChecking no
            UserKnownHostsFile /dev/null
            IdentityFile ....

and also add proper keys

### Prepare main configuration

Configuration should include both service node and provisioned nodes.
It described in json file (# xxx means comment and should removed):

    {
        "node":        "provisioner.a.b.c", # fqdn
        "ip_type":     "unmanaged", # configuration generator ignore that address
        "bmc_ip_type": "unmanaged", # ditto
        "role":        "", 
        "comment":     "dns, dhcp, tftp", 
        "t_machine_type": "",
        "t_exclude": "yes" #ignore for teuthology node description generation
    },
    {
        "node":         "client-1.a.b.c",
        "mac":          "aa:bb:cc:dd:ee:11", # mac address in management network
        "ip":           "10.11.12.11",       # ip address in management address
        "ip_type":      "dynamic",           # generate dhcp record for it
        "bmc_mac":      "aa:bb:cc:dd:ff:11", # bmc mac address if need
        "bmc_ip":       "10.11.12.111",      # bmc ip address
        "bmc_ip_type":  "dynamic",           # generate dhcp record for it
        "role":         "client",            # 
        "comment":      "",
        "t_machine_type": "t-client",        # generate sql record for teuthology 
        "t_exclude": "no"
    },

### Run service configuration generator

    python bin/make_cfgs_for_nodes.py

List of produced configuration files:

* dnsmasq configuration

    states/etc/dnsmasq/dnsmasq.d/nue_ses_network_nodes.conf

* salt configuration

    deploy.roster

* conman configuration file  (from template  states/etc/conman.conf.tmpl)
    states/etc/conman.conf

### Run remote node configuration.

Prepare host which will be used for PXE services setup

    sudo -u salt salt-ssh -i --roster-file nue_deploy.roster -c . 'head' '*' state.apply prepare -v  

### Boot directory preparation

Depends on specific hardware it could different process, so just now include some hints for
old-style BIOS boot:

* copy states.sample to your private dir

* find and place some binary files suited for your distro/hardware:
    <states>/tftp:
        boot
        grubx64.efi
        ldlinux.c32
        ldlinux.e64
        libutil.c32
        menu.c32
        pxelinux.0
        pxelinux.cfg
        shim-sles.efi
        syslinux.efi

* provide you own `pxelinux.cfg/default` based on `states.sample/tftp/pxelinux.cfg/default`

## How to add new image to PXE env:

TBD

## BUILD

as root on build node:

    cd kiwi/<distro>
    kiwi-ng-3 --color-output --debug --profile oem system build --description . --target <target dir>

## INSTALL

as user on build node:

    export PYTHONPATH=lib:bin
    bin/add_image.py

## Configuration

For manual node configuration could be used salt commands:

    sudo -u salt salt-ssh -i --roster-file nue_deploy.roster --key-deploy --passwd <password> -c . '<node name without domain>' state.apply setup_hsm

**PROVISION**   

Warning! curl comamnds will be changed in few weeks

for provision one node for testing boot could be use cmd. 'oem-' is important!

    curl -i http://10.162.230.2:5000/pxe/api/node/provision/ses-client-8/oem-sle-15sp1-0.0.3

for permanent switch os(with no version) install to latest image as default

    ... TBD ...

 and next provision could be done via aliasing

    curl -i http://10.162.230.2:5000/pxe/api/node/provision/ses-client-8/sle-15sp1

 Use    'opensuse-leap-15.0' for defaut opensuse 15.0

## Test execution

Unit tests are in 'test'  subdir and could be executed via

    python test/test_pelagos.py 

Teuthology integration could be tested via  executing 2 commands:

1. Run 

    python bin/pelagos.py -c test_pelagos_teuthology/test_network_cfg.json --simulate=fast  --tftp-dir=/tmp/tftp 

pytest test_pelagos.py -k test_create_5


## Notes

### Network  configuration

Service (provisioner) node should be able connect to management, bmc management networks in common case. If high-speed networks dhcp is also wanted please be take care about proper network configuration.

### Virtual environment

Tested manually with virtual bmc (https://github.com/openstack/virtualbmc) in libvirt environment and work ok  exclude console collection.
