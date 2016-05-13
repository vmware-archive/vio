import unittest

from shellutil import shell


class ShellTest(unittest.TestCase):
    def test_cmd_under_dir(self):
        shell.local("mkdir -p /tmp/test")
        with shell.cd("/tmp"):
            with shell.cd("/tmp/test"):
                code, output = shell.local("pwd")
                self.assertEqual(output, '/tmp/test\n')
            code, output = shell.local("pwd")
            self.assertEqual(output, '/tmp\n')


if __name__ == '__main__':
    unittest.main()
