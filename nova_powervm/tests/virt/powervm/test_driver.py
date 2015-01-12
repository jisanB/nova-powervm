# Copyright 2014, 2015 IBM Corp.
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import logging

import mock

from nova import test
from nova.virt import fake
from pypowervm.tests.wrappers.util import pvmhttp
from pypowervm.wrappers import constants as wpr_consts
import pypowervm.wrappers.managed_system as msentry_wrapper

from nova_powervm.virt.powervm import driver
from nova_powervm.virt.powervm import host as pvm_host

MS_HTTPRESP_FILE = "managedsystem.txt"
MS_NAME = 'HV4'

LOG = logging.getLogger(__name__)
logging.basicConfig()


class FakeInstance(object):
    def __init__(self):
        self.name = 'fake_instance'
        self.display_name = 'fake_display_name'
        self.instance_type_id = 'instance_type_id'
        self.uuid = 'fake_uuid'


class FakeFlavor(object):
    def __init__(self):
        self.name = 'fake_flavor'
        self.memory_mb = 256
        self.vcpus = 1


class TestPowerVMDriver(test.TestCase):
    def setUp(self):
        super(TestPowerVMDriver, self).setUp()

        ms_http = pvmhttp.load_pvm_resp(MS_HTTPRESP_FILE)
        self.assertNotEqual(ms_http, None,
                            "Could not load %s " %
                            MS_HTTPRESP_FILE)

        entries = ms_http.response.feed.findentries(
            wpr_consts.SYSTEM_NAME, MS_NAME)

        self.assertNotEqual(entries, None,
                            "Could not find %s in %s" %
                            (MS_NAME, MS_HTTPRESP_FILE))

        self.myentry = entries[0]
        self.wrapper = msentry_wrapper.ManagedSystem(self.myentry)

    def test_driver_create(self):
        """Validates that a driver of the PowerVM type can just be
        initialized.
        """
        test_drv = driver.PowerVMDriver(fake.FakeVirtAPI())
        self.assertIsNotNone(test_drv)

    @mock.patch('pypowervm.adapter.Session')
    @mock.patch('pypowervm.adapter.Adapter')
    @mock.patch('nova_powervm.virt.powervm.host.find_entry_by_mtm_serial')
    def test_driver_init(self, mock_find, mock_apt, mock_sess):
        """Validates the PowerVM driver can be initialized for the host."""
        drv = driver.PowerVMDriver(fake.FakeVirtAPI())
        drv.init_host('FakeHost')
        # Nothing to really check here specific to the host.
        self.assertIsNotNone(drv)

    @mock.patch('pypowervm.adapter.Session')
    @mock.patch('pypowervm.adapter.Adapter')
    @mock.patch('nova_powervm.virt.powervm.host.find_entry_by_mtm_serial')
    @mock.patch('nova_powervm.virt.powervm.vm.UUIDCache')
    @mock.patch('nova.context.get_admin_context')
    @mock.patch('nova.objects.flavor.Flavor.get_by_id')
    def test_driver_ops(self, mock_get_flv, mock_get_ctx,
                        mock_uuidcache, mock_find,
                        mock_apt, mock_sess):
        """Validates the PowerVM driver operations."""
        drv = driver.PowerVMDriver(fake.FakeVirtAPI())
        drv.init_host('FakeHost')
        drv.adapter = mock_apt

        # get_info()
        inst = FakeInstance()
        mock_uuidcache.lookup.return_value = '1234'
        drv.pvm_uuids = mock_uuidcache
        info = drv.get_info(inst)
        self.assertEqual(info.id, '1234')

        # list_instances()
        tgt_mock = 'nova_powervm.virt.powervm.vm.get_lpar_list'
        with mock.patch(tgt_mock) as mock_get_list:
            fake_lpar_list = ['1', '2']
            mock_get_list.return_value = fake_lpar_list
            inst_list = drv.list_instances()
            self.assertEqual(fake_lpar_list, inst_list)

        # spawn()
        with mock.patch('nova_powervm.virt.powervm.vm.crt_lpar') as mock_crt:
            my_flavor = FakeFlavor()
            mock_get_flv.return_value = my_flavor
            drv.spawn('context', inst, 'image_meta',
                      'injected_files', 'admin_password')
            mock_crt.assert_called_with(mock_apt, drv.host_uuid,
                                        inst, my_flavor)

    @mock.patch('nova_powervm.virt.powervm.driver.LOG')
    def test_log_op(self, mock_log):
        """Validates the log_operations."""
        drv = driver.PowerVMDriver(fake.FakeVirtAPI())
        inst = FakeInstance()

        drv._log_operation('fake_op', inst)
        entry = ('Operation: fake_op. Virtual machine display name: '
                 'fake_display_name, name: fake_instance, UUID: fake_uuid')
        mock_log.info.assert_called_with(entry)

    def test_host_resources(self):
        stats = pvm_host.build_host_resource_from_entry(self.wrapper)
        self.assertIsNotNone(stats)

        # Check for the presence of fields
        fields = (('vcpus', 500), ('vcpus_used', 0),
                  ('memory_mb', 5242880), ('memory_mb_used', 128),
                  'local_gb', 'local_gb_used', 'hypervisor_type',
                  'hypervisor_version', 'hypervisor_hostname', 'cpu_info',
                  'supported_instances', 'stats')
        for fld in fields:
            if isinstance(fld, tuple):
                value = stats.get(fld[0], None)
                self.assertEqual(value, fld[1])
            else:
                value = stats.get(fld, None)
                self.assertIsNotNone(value)
        # Check for individual stats
        hstats = (('proc_units', '500.00'), ('proc_units_used', '0.00'))
        for stat in hstats:
            if isinstance(stat, tuple):
                value = stats['stats'].get(stat[0], None)
                self.assertEqual(value, stat[1])
            else:
                value = stats['stats'].get(stat, None)
                self.assertIsNotNone(value)
