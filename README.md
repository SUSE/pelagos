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

### Configure ssh password-less access

in `~/.ssh/config` add

    Host a.b.c.d
            User root
            StrictHostKeyChecking no
            UserKnownHostsFile /dev/null
            IdentityFile ....

and also add proper keys

### Prepare Pelagos configuration file

Configuration should include both service node and provisioned nodes.
It described in json file (# xxx means comment and should removed):

    {

    "ipmi_user": "root",
    "ipmi_pass": "password",
    "target_node_password": "password",
    # record for maintenance pxe records
    "maintenance_image_kernel": "opensuse-leap-15.0.x86_64-0.0.1-4.12.14-lp150.11-default.kernel",
    "maintenance_image_initrd": "opensuse-leap-15.0-image.x86_64-0.0.1.initrd.xz",
    "default_pxe_server": "127.0.0.1",
    "domain": "a.b.c.de"
    "nodes":[
        {
            "node":      "provisioner.a.b.c", # node name or fqdn, is used
                                                # also for salt call after
                                                # provisining
            "boot_node": "node or fqdn", # ip name is used for boot if the
                                         # name is used only for boot and 
                                         # the name is not used in cluster and
                                         # teuthology networking
            "ip_type":     "unmanaged", # configuration generator ignore that
                                        #address
            "bmc_ip_type": "unmanaged", # ditto
            "role":        "client", # not used now, reserved
            "comment":     "dns, dhcp, tftp",
            "t_machine_type": "", # teuthology 'machine type' label
            "t_exclude": "yes" # ignore for teuthology node description generation
            "provision_need_reboot": "yes" # if reboot after provision is needed

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
        }
    }

### Run service configuration generator

_It is optional step and configuration could be provided
manually_

Prepare  directory for configuration files, e.g. copy from sample
    cp -r states.sample <cfg dir>/states


and edit it. Add pillar directory if needed.
Next is generating configuration files based on Pelagos configuration file

    bin/make_cfgs.py -c <pelagos cfg file> -d <cfg dir>

List of produced configuration files in target dir:

* dnsmasq configuration

    states/etc/dnsmasq/dnsmasq.d/nue_ses_network_nodes.conf

* salt configuration

    deploy.roster

* conman configuration file  (from template  states/etc/conman.conf.tmpl)
    states/etc/conman.conf

* teuthology sql script for create nodes

### Prepare salt env

_It is optional step and configuration could be provided
manually_

Copy salt master file and correct it with adding directory with configuration
 files (see below)

    cp master.sample master

Add to 'states' cfg directory with generated files

### Run pxe node remote configuration

Prepare host which will be used for PXE services setup

    sudo -u salt salt-ssh -i --roster-file  deploy.roster -c . 'pxe node node' '*' state.apply prepare -v

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

TODO provide kiwi samples 

as root on build node:

    cd kiwi/<distro>
    kiwi-ng-3 --color-output --debug --profile oem system build --description . --target <target dir>

## INSTALL

as user on build node:

    export PYTHONPATH=lib:bin
    bin/add_image.py

## Configuration

For manual provisioned node configuration could be used salt commands:

    sudo -u salt salt-ssh -i --roster-file deploy.roster --key-deploy --passwd <password> -c . '<node name without domain>' state.apply setup_hsm

## Provisioning

Warning! curl commands is subject for change

* 'os' - os version which used for boot. It compatible with
        teuthology format, e.g. can be ' sle-15.1'. Also
        supported 2 special 'os'-es:
         - 'local' - boot for local disk
         - 'maintenance_image' - maintenance disk ram-only image, also it
            used as 'parking' image in unlock command


* 'node' - node name as defined in pelagos configuration

* 'add_sls' - add node specific salt script to provisioning. Mostly it is
    needed for specific or debug configuration.

For provision one node for testing boot could be use cmd.

    curl -i http://<server ip>:5000/node/provision -X POST \
    -F 'os=<os>' -F 'node=<node>'  [-F 'add_sls=sls_name']

Provisioning status could be observed

    curl  http://<server ip>:5000/tasks/statuses

for permanent switch os(with no version) install to latest image as default

    ... TBD ...

## Reprovisioning and dissmissing provision

Pelagos do some actions after provision start: change boot files,
observer conman log files, trying to connect to a target node and so on,
in some cases a provision thread could decide to reboot a node. All that
activity could be problematic for a concurrent provision and re-provision. 

For solving it, added a special functionality for a dismissing provision for
specific node. It prevents 2 and more simultaneous provisions for one node.
For REST 'node/provision' the functionality call automatically.

Also, there is special call '/node/dismiss' if a user want to do it explicitly.
Parameters are: 
* 'node' - a node name from the configuration file which should be dismissed
    from control a thread

## Test execution

### Pelagos unit tests

Unit tests are in 'test' subdir and could be executed via

    python test/test_pelagos.py

or for specific test case
   python test/test_pelagos.py pelagosTest.test_provision_log_cleanup 

### Integration test

Teuthology integration could be tested via  executing 2 commands:

1. Run Pelagos in python pelgos env

        python bin/pelagos.py --config test_pelagos_teuthology/test_network_cfg.json --simulation=fast  --tftpdir=/tmp/tftp

2. Run test in teuthology env with adding teuthology lib

        pytest test_pelagos.py -k test_create_5

## Notes

### Network  configuration

Service (provisioner) node should be able connect to management, bmc management networks in common case. If high-speed networks dhcp is also wanted please be take care about proper network configuration.

### Virtual environment

Tested manually with virtual bmc (https://github.com/openstack/virtualbmc) in libvirt environment and work ok  exclude console collection.
