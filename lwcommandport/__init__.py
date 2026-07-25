from __future__ import print_function

__author__     = "Bob Hood"
__copyright__  = "Copyright (C) 2015 NewTek, Inc."
__version__    = "1.0"
__maintainer__ = "Bob Hood"
__email__      = "bobhood@lightwave3d.com"
__status__     = "Production"

# make sure any of our sub-modules (e.g., "layout") can be found
import pkgutil
__path__ = pkgutil.extend_path(__path__, __name__)

import os, sys
import ctypes
import socket
import hashlib
import fnmatch
import subprocess

if os.name != 'nt':
    try:
        from subprocess import DEVNULL      # Python 3.x
    except:
        DEVNULL = open(os.devnull, 'wb')

# These values must match their source values in lwcomport.h

CP_DISCOVERY_START = 50155
CP_DISCOVERY_END = 50165

CP_COMMANDSET_LAYOUT = 1
CP_COMMANDSET_MODELER = 2

CP_REQ_MAGIC = (((ord('C'))<<24)|((ord('R'))<<16)|((ord('E'))<<8)|(ord('Q')))
CP_INFO_MAGIC = (((ord('C'))<<24)|((ord('N'))<<16)|((ord('F'))<<8)|(ord('O')))

COMMANDPORT_REQ_VERSION = 1
class CommandPortReq(ctypes.Structure):
    _fields_ = [("magic", ctypes.c_int),
                ("version", ctypes.c_int),
                ("port", ctypes.c_ushort),
                ("dummy", ctypes.c_ushort)]

COMMANDPORT_INFO_VERSION = 2
class CommandPortInfo(ctypes.Structure):
    _fields_ = [("magic", ctypes.c_int),
                ("version", ctypes.c_int),
                ("major", ctypes.c_ushort),
                ("minor", ctypes.c_ushort),
                ("build", ctypes.c_ushort),
                ("app", ctypes.c_ushort),
                ("port", ctypes.c_ushort),
                ("port_alias", ctypes.c_char * 128)]

class CommandPort(object):
    """
    This is a base class for the Command Port system.  It is
    subclassed by the Layout and Modeler classes to provide
    common support.

    It is not intended for direct usage.
    """
    def __init__(self, address, port):
        super(CommandPort, self).__init__()

        self._address = address
        self._port = self._port_name_to_number(port)

        self._sock = None

    def _send_command(self, command, args=None):
        if (args is not None) and len(args):
            if sys.version_info[0] > 2:
                command = "{0} {1}".format(command, " ".join([str(t) for t in args]))
            else:
                command = "%s %s" % (command, " ".join([str(t) for t in args]))
            #print('sending "'+command+'" to '+self._address+':'+str(self._port))
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self._sock is not None:
            if sys.version_info[0] > 2:
                self._sock.sendto(command.encode("utf-8"), (self._address, self._port))
            else:
                self._sock.sendto(command, (self._address, self._port))

    def _port_name_to_number(self, port):
        if not isinstance(port, str):
            port = str(port)

        try:
            return int(port)
        except:
            pass

        m = hashlib.md5()
        if sys.version_info[0] > 2:
            m.update(port.encode("utf-8"))
        else:
            m.update(port)
        h = m.digest()
        hash = 0
        for i in range(len(h)):
            if sys.version_info[0] > 2:
                hash += (h[i] << i)
            else:
                hash += (ord(h[i]) << i)

        return (hash + 1024) % 65534

    def __common_walker(path, version, pattern):
        def file_visitor_2(args, thisdir, nameshere):
            (matches, version, pattern) = args
            for name in nameshere:
                fullpath = os.path.join(thisdir, name)
                if fnmatch.fnmatch(name, pattern) and (version in fullpath):
                    matches.append(fullpath)

        files = []

        if sys.version_info[0] > 2:
            os.path.walk(path, file_visitor_2, (files, version, pattern))
        else:
            for root, dirs, files in os.walk(path):
                fullpath = os.path.join(root, name)
                if fnmatch.fnmatch(name, pattern) and (version in fullpath):
                    files.append(fullpath)

        return files

    def _launch(self, module, *args, **kwargs):
        if sys.version_info[0] > 2:
            if (not isinstance(module, (str, bytes))) or (len(module) == 0):
                return (False, 'Invalid argument type provided!')
        else:
            if (not isinstance(module, (str, unicode))) or (len(module) == 0):
                return (False, 'Invalid argument type provided!')

        if os.path.exists(module):
            # they are specifying the executable to launch, so just us it
            launch_args = []
            for arg in args:
                if isinstance(arg, (list, tuple)):
                    launch_args.extend(arg)
                else:
                    launch_args.append(arg)

            command = [module] + launch_args
            print(command)
            try:
                pid = subprocess.Popen(command).pid
            except:
                return (False, 'Failed to launch process "%s"!' % module)
        else:
            if (str(module.lower()) != 'layout') and (str(module.lower()) != 'modeler'):
                return (False, 'Invalid argument value ("%s") provided!' % module)

            version = kwargs.get("version", None)

            # see if we can figure out where the executable has been placed

            if os.name == 'nt':
                path = ""

                # one of these will succeed
                try:
                    import winreg as reg        # v3
                except:
                    try:
                        import _winreg as reg   # v2
                    except:
                        return (False, 'The winreg module must be available to auto-detect your install path!')

                if version is None:
                    try:
                        key = reg.OpenKey(reg.HKEY_LOCAL_MACHINE,
                                          r"SOFTWARE\NewTek\LightWave", 0)
                    except:
                        return (False, 'LightWave does not appear to be installed on your machine!')

                    # enumerate the key values here to process
                    # each potential installed version
                    index = 0
                    versions = []
                    while True:
                        try:
                            data = reg.EnumKey(key, index)
                        except:
                            break
                        versions.append(data)
                        index += 1

                    reg.CloseKey(key);

                    # sort them lexically and then start checking from newest to oldest
                    versions.sort(reverse=True)
                    best_version = None
                    for version in versions:
                        try:
                            key = reg.OpenKey(reg.HKEY_LOCAL_MACHINE,
                                              r"SOFTWARE\NewTek\LightWave\%s\x64" % version,
                                              0)
                            path, type = reg.QueryValueEx(key, "ApplicationPath")
                            reg.CloseKey(key)

                            if os.path.exists(path):
                                best_version = path
                                break
                        except:
                            pass

                    if best_version is None:
                        return (False, 'LightWave does not appear to be installed on your machine!')
                else:
                    try:
                        key = reg.OpenKey(reg.HKEY_LOCAL_MACHINE,
                                          r"SOFTWARE\NewTek\LightWave\%s.0\x64" % version,
                                          0)
                    except:
                        return (False, 'LightWave does not appear to be installed on your machine!')

                    path, type = reg.QueryValueEx(key, "ApplicationPath")
                    reg.CloseKey(key)

                if not os.path.exists(path):
                    return (False, 'Cannot detect LightWave installation!')

                if str(module.lower()) == 'layout':
                    module = os.path.join(path, 'bin', 'Layout.exe')
                    if not os.path.exists(module):
                        module = os.path.join(path, 'bin', 'Layout_db.exe')
                    if not os.path.exists(module):
                        return (False, 'Cannot locate Layout executable!')
                elif str(module.lower()) == 'modeler':
                    module = os.path.join(path, 'bin', 'Modeler.exe')
                    if not os.path.exists(module):
                        module = os.path.join(path, 'bin', 'Modeler_db.exe')
                    if not os.path.exists(module):
                        return (False, 'Cannot locate Modeler executable!')
            elif sys.platform == 'darwin':
                files = []
                path = '/Applications/NewTek'
                if not os.path.exists(path):
                    return (False, 'LightWave does not appear to be installed on your machine!')

                if version is None:
                    # enumerate installed versions and use the most current
                    folders = os.listdir(path)
                    if len(folders) == 0:
                        return (False, 'LightWave does not appear to be installed on your machine!')
                    folders.sort(reverse=True)

                    app = ""
                    if str(module.lower()) == 'layout':
                        app = "Layout"
                    elif str(module.lower()) == 'modeler':
                        app = "Modeler"

                    for folder in folders:
                        module = os.path.join(path, folder, "%s.app" % app, "Contents", "MacOS", app)
                        if os.path.exists(module):
                            break
                        module = None

                    if module is None:
                        return (False, 'Cannot locate %s app!' % app)
                else:
                    if str(module.lower()) == 'layout':
                        files = self.__common_walker(path, version, "Layout*.app")
                        if len(files) == 0:
                            return (False, 'Cannot detect LightWave installation!')
                        module = os.path.join(path, files[0], 'Contents', 'MacOS', 'Layout')
                        if not os.path.exists(module):
                            return (False, 'Cannot locate Layout app!')
                    elif str(module.lower()) == 'modeler':
                        files = self.__common_walker(path, version, "Modeler*.app")
                        if len(files) == 0:
                            return (False, 'Cannot detect LightWave installation!')
                        module = os.path.join(path, files[0], 'Contents', 'MacOS', 'Modeler')
                        if not os.path.exists(module):
                            return (False, 'Cannot locate Modeler app!')
            else:
                # Linux
                files = []
                path = '/opt/NewTek'

                if str(module.lower()) == 'layout':
                    files = self.__common_walker(path, version, "Layout*")
                    if len(files) == 0:
                        return (False, 'Cannot detect LightWave installation!')
                    module = os.path.join(path, files[0])
                    if not os.path.exists(module):
                        return (False, 'Cannot locate Layout executable!')
                elif str(module.lower()) == 'modeler':
                    files = self.__common_walker(path, version, "Modeler*")
                    if len(files) == 0:
                        return (False, 'Cannot detect LightWave installation!')
                    module = os.path.join(path, files[0])
                    if not os.path.exists(module):
                        return (False, 'Cannot locate Modeler executable!')

            cmd = []
            for arg in args:
                if isinstance(arg, (list, tuple)):
                    cmd.extend(arg)
                else:
                    cmd.append(arg)
            cmd.insert(0, module)

            if os.name == 'nt':
                try:
                    pid = subprocess.Popen(cmd).pid
                except:
                    return (False, 'Failed to launch process "%s"!' % module)
            else:
                try:
                    pid = subprocess.Popen(cmd, stdin=DEVNULL, stdout=DEVNULL, stderr=subprocess.STDOUT).pid
                except:
                    return (False, 'Failed to launch process "%s"!' % module)

        return (True, '')

    def Ring(self, topic, command):
        """ Ring(prefix, command) """
        if sys.version_info[0] > 2:
            command = "{{0}} {1}".format(topic, command)
        else:
            command = "{%s} %s" % (topic, command)
        self._send_command(command, None)