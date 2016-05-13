import unittest

from sshutil import remote


class RemoteTest(unittest.TestCase):
    def test_run_with_capture(self):
        rc = remote.RemoteClient('nimbus-gateway.eng.vmware.com',
                                 'vio-autouser', '!ya6u4uWY2u@egYvU')
        self.assertEqual(rc.run('pwd'), '/mts/home1/vio-autouser\n')

    def test_run_without_capture(self):
        rc = remote.RemoteClient('nimbus-gateway.eng.vmware.com',
                                 'vio-autouser', '!ya6u4uWY2u@egYvU')
        self.assertEqual(rc.run('pwd', capture=False), '')


if __name__ == '__main__':
    unittest.main()
