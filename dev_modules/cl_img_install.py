#!/usr/bin/env python
#
# Copyright (C) 2014, Cumulus Networks www.cumulusnetworks.com
#
#
DOCUMENTATION = '''
---
module: cl_img_install
author: Stanley Karunditu
short_description: Install a different Cumulus Linux version.
description:
    - install a different version of Cumulus Linux in the inactive slot.
options:
    src:
        description:
            - full path to the Cumulus Linux binary image. \
Can be a local path, http or https URL.  \
If the code version is in the name of the file, the module will assume this \
is the version of code you wish to install.
        required: true
    version:
        description:
            -  inform the module of the exact version one is  installing. \
This overrides the automatic check of version in the file name. \
For example, if the binary file name \
is called CumulusLinux-2.2.3.bin, and version is set to '2.5.0', \
then the module will assume it \
is installing '2.5.0' not '2.2.3'. If version is not included, \
then the module will assume '2.2.3' \
is the version to install.
    switch_slot:
        description:
            - Switch slots after installing the image. \
To run the installed code, reboot the switch
        choices: ['yes', 'no']
        default: 'no'

requirements: ["Cumulus Linux OS"]
notes:
    - Image Management Documentation - \
http://cumulusnetworks.com/docs/2.2/user-guide/system_management_diagnostics/img-mgmt.html#upgrade
    - Contact Cumulus Networks @ http://cumulusnetworks.com/contact/
'''
EXAMPLES = '''
Example playbook entries using the cl_img_install module

    tasks:
    - name: install image using using http url. Do not reboot the switch to \
run the new release
      cl_img_install: version=2.0.1 \
          src='http://10.1.1.1/CumulusLinux-2.0.1.bin'
          switch_slot=yes

## Copy the software using get_url to the switch local system and
## install the software
    - name: download cumulus linux to local system
      get_url: src=ftp://cumuluslinux.bin dest=/root/CumulusLinux-2.0.1.bin
    - name: install image from local filesystem. Get version from the filename
      cl_img_install:  src='/root/CumulusLinux-2.0.1.bin'

    - name: install image and switch slots. only reboot needed
      cl_img_install: version=2.0.1 src=/root/image.bin switch_slot=yes'
'''


def check_url(module, url):
    parsed_url = urlparse(url)
    if len(parsed_url.path) > 0:
        sch = parsed_url.scheme
        if (sch == 'http' or sch == 'https' or len(parsed_url.scheme) == 0):
            return True
    module.fail_json(msg="Image Path URL. Wrong Format %s" % (url))
    return False


def run_cl_cmd(module, cmd, check_rc=True):
    try:
        (rc, out, err) = module.run_command(cmd, check_rc=check_rc)
    except Exception, e:
        module.fail_json(msg=e.strerror)
    # trim last line as it is always empty
    ret = out.splitlines()
    return ret


def get_slot_info(module):
    slots = {}
    slots['1'] = {}
    slots['2'] = {}
    active_slotnum = get_active_slot(module)
    primary_slotnum = get_primary_slot_num(module)
    for _num in range(1, 3):
        slot = slots[str(_num)]
        slot['version'] = get_slot_version(module, str(_num))
        if _num == int(active_slotnum):
            slot['active'] = True
        if _num == int(primary_slotnum):
            slot['primary'] = True
    return slots


def get_slot_version(module, slot_num):
    lsb_release = check_mnt_root_lsb_release(slot_num)
    switch_firm_ver = check_fw_print_env(module, slot_num)
    _version = module.sw_version
    if lsb_release == _version or switch_firm_ver == _version:
        return _version
    elif lsb_release:
        return lsb_release
    else:
        return switch_firm_ver


def check_mnt_root_lsb_release(slot_num):
    _path = '/mnt/root-rw/config%s/etc/lsb-release' % (slot_num)
    try:
        lsb_release = open(_path)
        lines = lsb_release.readlines()
        for line in lines:
            _match = re.search('DISTRIB_RELEASE=([0-9a-zA-Z.]+)', line)
            if _match:
                return _match.group(1).split('-')[0]
    except:
        pass
    return None


def check_fw_print_env(module, slot_num):
    cmd = "/usr/sbin/fw_printenv -n cl.ver%s" % (slot_num)
    output = run_cl_cmd(module, cmd)
    return output[0].split('-')[0]


def get_primary_slot_num(module):
    cmd = "/usr/sbin/fw_printenv -n cl.active"
    return ''.join(run_cl_cmd(module, cmd))


def get_active_slot(module):
    try:
        cmdline = open('/proc/cmdline').readline()
    except:
        module.fail_json(msg='Failed to open /proc/cmdline. ' +
                         'Unable to determine active slot')

    _match = re.search('active=(\d+)', cmdline)
    if _match:
        return _match.group(1)
    return None


def install_img(module):
    src = module.params.get('src')
    _version = module.sw_version
    app_path = '/usr/cumulus/bin/cl-img-install -f %s' % (src)
    run_cl_cmd(module, app_path)
    perform_switch_slot = module.params.get('switch_slot')
    if perform_switch_slot is True:
        check_sw_version(module)
    else:
        _changed = True
        _msg = "Cumulus Linux Version " + _version + " successfully" + \
            " installed in alternate slot"
        module.exit_json(changed=_changed, msg=_msg)


def switch_slot(module, slotnum):
    _switch_slot = module.params.get('switch_slot')
    if _switch_slot is True:
        app_path = '/usr/cumulus/bin/cl-img-select %s' % (slotnum)
        run_cl_cmd(module, app_path)


def determine_sw_version(module):
    _version = module.params.get('version')
    _filename = ''
    # Use _version if user defines it
    if _version:
        module.sw_version = _version
        return
    else:
        _filename = module.params.get('src').split('/')[-1]
        _match = re.search('\d+\W\d+\W\w+', _filename)
        if _match:
            module.sw_version = re.sub('\W', '.', _match.group())
            return
    _msg = 'Unable to determine version from file %s' % (_filename)
    module.exit_json(changed=False, msg=_msg)


def check_sw_version(module):
    slots = get_slot_info(module)
    _version = module.sw_version
    perform_switch_slot = module.params.get('switch_slot')
    for _num, slot in slots.items():
        if slot['version'] == _version:
            if 'active' in slot:
                _msg = "Version %s is installed in the active slot" \
                    % (_version)
                module.exit_json(changed=False,  msg=_msg)
            else:
                _msg = "Version " + _version + \
                    " is installed in the alternate slot. "
                if 'primary' not in slot:
                    if perform_switch_slot is True:
                        switch_slot(module, _num)
                        _msg = _msg + \
                            "cl-img-select has made the alternate " + \
                            "slot the primary slot. " +\
                            "Next reboot, switch will load " + _version + "."
                        module.exit_json(changed=True, msg=_msg)
                    else:
                        _msg = _msg + \
                            "Next reboot will not load " + _version + ". " + \
                            "switch_slot keyword set to 'no'."
                        module.exit_json(changed=False, msg=_msg)
                else:
                    if perform_switch_slot is True:
                        _msg = _msg + \
                            "Next reboot, switch will load " + _version + "."
                        module.exit_json(changed=True, msg=_msg)
                    else:
                        _msg = _msg + \
                            'switch_slot set to "no". ' + \
                            'No further action to take'
                        module.exit_json(changed=False, msg=_msg)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            src=dict(required=True, type='str'),
            version=dict(type='str'),
            switch_slot=dict(type='bool', choices=BOOLEANS, default=False),
        ),
    )

    determine_sw_version(module)
    _url = module.params.get('src')

    check_sw_version(module)

    check_url(module, _url)

    install_img(module)


# import module snippets
from ansible.module_utils.basic import *
# incompatible with ansible 1.4.4 - ubuntu 12.04 version
# from ansible.module_utils.urls import *
from urlparse import urlparse
import re

if __name__ == '__main__':
    main()
