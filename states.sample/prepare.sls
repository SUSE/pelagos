#sudo -u salt salt-ssh -i --roster-file nue_deploy.roster -c . '*' state.apply prepare

install additional packages:
  pkg.installed:
    - pkgs:
      - rsync
      - dnsmasq
      - curl
      - ipmitool      
      - apache2
      - apache2-utils
      - atftp
      - nmap
      - conman
      - python3-setuptools
      
/etc/dnsmasq.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.conf

/etc/dnsmasq.d/:
  file.directory:
    - user: root
    - group: root
    - dir_mode: 755
    - makedirs: true

/etc/dnsmasq.d/default_boot_menu.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/default_boot_menu.conf

/etc/dnsmasq.d/dhcp.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/dhcp.conf

/etc/dnsmasq.d/main.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/main.conf

/etc/dnsmasq.d/pxe.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/pxe.conf

/etc/dnsmasq.d/tftp.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/tftp.conf

/etc/dnsmasq.d/nue_ses_network.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/network.conf

/etc/dnsmasq.d/nue_ses_network_nodes.conf:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/network_nodes.conf


/etc/dnsmasq.d/hosts:
  file.managed:
    - source: salt://etc/dnsmasq/dnsmasq.d/hosts


/srv/tftpboot/boot:
  file.directory:
    - user: root
    - group: root
    - dir_mode: 755
    - makedirs: true

/srv/tftpboot/pxelinux.cfg:
  file.directory:
    - user: root
    - group: root
    - dir_mode: 755

/srv/tftpboot/image:
  file.directory:
    - user: root
    - group: root
    - dir_mode: 755

/srv/tftpboot/KIWI:
  file.directory:
    - user: root
    - group: root
    - dir_mode: 755

/srv/tftpboot/pxelinux.cfg/default:
  file.managed:
    - source: salt://tftp/pxelinux.cfg/default

/srv/tftpboot/pxelinux.0:
  file.managed:
    - source: salt://tftp/pxelinux.0
    - mode: 755

/srv/tftpboot/ldlinux.e64:
  file.managed:
    - source: salt://tftp/ldlinux.e64
    - mode: 755

/srv/tftpboot/shim-sles.efi:
  file.managed:
    - source: salt://tftp/shim-sles.efi
    - mode: 755

/srv/tftpboot/syslinux.efi:
  file.managed:
    - source: salt://tftp/syslinux.efi
    - mode: 755


/etc/sysconfig/atftpd:
  file.managed:
    - source: salt://etc/sysconfig/atftpd
    - mode: 755

/etc/apache2/default-server.conf:
  file.managed:
    - source: salt://etc/apache2/default-server.conf
    - mode: 755


/srv/www/htdocs/:
  file.directory:
    - user: root
    - group: root
    - dir_mode: 755
    - makedirs: true

/srv/www/htdocs/image:
  file.symlink:
      - target: /srv/tftpboot/image

/srv/www/htdocs/boot:
  file.symlink:
      - target: /srv/tftpboot/boot

/etc/conman.conf:
  file.managed:
    - source: salt://etc/conman.conf
    - mode: 644

/var/log/conman:
  file.directory:
    - user: root
    - group: root
    - dir_mode: 755
    - makedirs: true

atftpd.socket:
  service.running:
    - enable: True
    - restart: True

'killall atftpd':
   cmd.run

'systemctl stop  atftpd.socket ; sleep 5':
   cmd.run
'systemctl start atftpd.socket':
   cmd.run

apache2:
  service.running:
    - enable: True
    - restart: True

'systemctl restart apache2':
  cmd.run

dnsmasq:
  service.running:
    - enable: True

'systemctl restart dnsmasq':
  cmd.run

conman:
  service.running:
    - enable: True

'systemctl restart conman':
  cmd.run

