""" test """
import logging
import random
import sys
import tempfile
import datetime
from _socket import SOCK_STREAM, AF_INET

import requests

from bzt.engine import Engine, Configuration, FileLister, HavingInstallableTools
from bzt.engine import Provisioning, ScenarioExecutor, Reporter
from bzt.modules.aggregator import ResultsReader, AggregatorListener
from bzt.modules.functional import FunctionalResultsReader
from bzt.six import b
from bzt.utils import load_class, to_json, get_full_path, get_uniq_name, FileReader, is_windows
from . import random_sample, TEST_DIR

try:
    from exceptions import KeyboardInterrupt
except ImportError:
    # noinspection PyUnresolvedReferences
    from builtins import KeyboardInterrupt


class MockFileReader(FileReader):
    SYS_ENCODING = 'cp1251' if is_windows() else 'utf-8'


class EngineEmul(Engine):
    def __init__(self):
        super(EngineEmul, self).__init__(logging.getLogger(''))

        directory = get_full_path(TEST_DIR)
        prefix = datetime.datetime.now().strftime(self.ARTIFACTS_DIR)
        self.config.merge({
            "provisioning": "local",
            "modules": {
                "mock": ModuleMock.__module__ + "." + ModuleMock.__name__,
                "local": ModuleMock.__module__ + "." + ModuleMock.__name__},
            "settings": {
                "check-updates": False,
                "artifacts-dir": get_uniq_name(directory=directory, prefix=prefix)}})

        self.create_artifacts_dir()
        self.prepare_exc = None
        self.was_finalize = False

    def dump_config(self):
        """ test """
        fname = tempfile.mkstemp()[1]
        self.config.dump(fname, Configuration.JSON)
        with open(fname) as fh:
            logging.debug("JSON:\n%s", fh.read())

    def prepare(self):
        if self.prepare_exc:
            raise self.prepare_exc
        return super(EngineEmul, self).prepare()


class ModuleMock(ScenarioExecutor, Provisioning, Reporter, FileLister, HavingInstallableTools):
    """ mock """

    def __init__(self):
        super(ModuleMock, self).__init__()
        self.postproc_exc = None
        self.check_exc = None
        self.prepare_exc = None
        self.startup_exc = None
        self.shutdown_exc = None

        self.check_iterations = sys.maxsize

        self.was_shutdown = False
        self.was_startup = False
        self.was_prepare = False
        self.was_check = False
        self.was_postproc = False

        self.is_has_results = False

    def prepare(self):
        """
        :raise self.prepare_exc:
        """
        self.log.info("Preparing mock")
        self.was_prepare = True
        self.check_iterations = int(self.settings.get('check_iterations', "2"))
        self.postproc_exc = self.get_exc("postproc")
        self.check_exc = self.get_exc("check")
        self.prepare_exc = self.get_exc("prepare")
        self.startup_exc = self.get_exc("startup")
        self.shutdown_exc = self.get_exc("shutdown")

        if isinstance(self.engine.aggregator, ResultsReader):
            reader = MockReader()
            for num in range(0, self.check_iterations):
                for quan in range(0, int(random.random() * 10)):
                    reader.data.append(random_sample(num))
            # noinspection PyUnresolvedReferences
            self.engine.aggregator.add_reader(reader)

        if self.prepare_exc:
            raise self.prepare_exc

    def startup(self):
        """
        :raise self.startup_exc:
        """
        self.log.info("Startup mock")
        self.was_startup = True
        if self.startup_exc:
            raise self.startup_exc

    def check(self):
        """
        :return: :raise self.check_exc:
        """
        self.was_check = True
        self.log.info("Checks remaining: %s", self.check_iterations)
        self.check_iterations -= 1
        if not self.check_iterations:
            if self.check_exc:
                raise self.check_exc
            else:
                return True
        return False

    def shutdown(self):
        """
        :raise self.shutdown_exc:
        """
        self.log.info("Shutdown mock")
        self.was_shutdown = True
        if self.shutdown_exc:
            raise self.shutdown_exc

    def post_process(self):
        """
        :raise self.postproc_exc:
        """
        self.log.info("Postproc mock")
        self.was_postproc = True
        if self.postproc_exc:
            raise self.postproc_exc

    def get_exc(self, param):
        """
        :type param: str
        :return:
        """
        name = self.settings.get(param, "")
        if name:
            cls = load_class(name)
            return cls()
        return None

    def resource_files(self):
        """


        :return:
        """
        self.execution.get('files', []).append(__file__)
        return [__file__]

    def has_results(self):
        return self.is_has_results

    def install_required_tools(self):
        self.log.debug("All is good")


class MockReader(ResultsReader, AggregatorListener):
    """
    test
    """

    def __init__(self):
        super(MockReader, self).__init__()
        self.results = []
        self.data = []
        self.add_listener(self)
        self.track_percentiles = [0, 50, 90, 99, 99.5, 100]

    def _read(self, final_pass=False):
        """
        Emulating read samples

        :type final_pass: bool
        :return:
        """
        while self.data:
            # logging.debug("Emul read: %s", self.data[0])
            yield self.data.pop(0)

    def aggregated_second(self, data):
        """
        Store and assert aggregate sequence

        :type data: dict
        :raise AssertionError:
        """
        if self.results:
            if self.results[-1]["ts"] >= data["ts"]:
                raise AssertionError("TS sequence wrong: %s>=%s" % (self.results[-1]["ts"], data["ts"]))
        logging.info("Data: %s", data)
        self.results.append(data)


class MockFunctionalReader(FunctionalResultsReader):
    def __init__(self):
        super(MockFunctionalReader, self).__init__()
        self.data = []

    def read(self, last_pass=False):
        while self.data:
            yield self.data.pop(0)


# noinspection PyUnusedLocal
def download_progress_mock(blocknum, blocksize, totalsize):
    pass


class ResultChecker(AggregatorListener):
    def __init__(self, callback):
        super(ResultChecker, self).__init__()
        self.callback = callback

    def aggregated_second(self, data):
        self.callback(data)


class SocketEmul(object):
    # noinspection PyUnusedLocal
    def __init__(self, family=AF_INET, atype=SOCK_STREAM, proto=0, _sock=None):
        self.recv_data = b("")
        self.sent_data = b("")

    def connect(self, address):
        logging.debug("Emulated connect to %s", address)

    # noinspection PyUnusedLocal
    def recv(self, buf_size, flags=None):
        data = self.recv_data[:buf_size]
        self.recv_data = self.recv_data[buf_size + 1:]
        logging.debug("Emulated recv: %s", data)
        return data

    # noinspection PyUnusedLocal
    def send(self, data, flags=None):
        self.sent_data += data
        logging.debug("Emulated send: %s", data)

    def setblocking(self, state):
        logging.debug("Emulate setblocking=%s", state)

    def fileno(self):
        return 0

    def close(self):
        logging.debug("Emulated close")


class BZMock(object):
    def __init__(self, obj=None):
        """
        :type obj: bzt.bza.BZAObject
        """
        super(BZMock, self).__init__()
        locs = [{'id': 'aws', 'sandbox': False, 'title': 'AWS'},
                {'id': 'us-east-1', 'sandbox': False, 'title': 'East'},
                {'id': 'us-west', 'sandbox': False, 'title': 'Dallas (Rackspace)'},
                {'id': 'harbor-sandbox', 'sandbox': True, 'title': 'Sandbox'},
                {'id': 'non-harbor-sandbox', 'sandbox': True, 'title': 'Sandbox Neverexisting'}, ]
        self.mock_get = {
            'https://a.blazemeter.com/api/v4/web/version': {},
            'https://a.blazemeter.com/api/v4/user': {'defaultProject': {'id': None}},
            'https://a.blazemeter.com/api/v4/accounts': {"result": [{'id': 1}]},
            'https://a.blazemeter.com/api/v4/workspaces?accountId=1&enabled=true&limit=100': {
                "result": [{'id': 1, 'enabled': True}]},
            'https://a.blazemeter.com/api/v4/multi-tests?workspaceId=1&name=Taurus+Cloud+Test': {"result": []},
            'https://a.blazemeter.com/api/v4/tests?workspaceId=1&name=Taurus+Cloud+Test': {"result": []},
            'https://a.blazemeter.com/api/v4/projects?workspaceId=1&limit=99999': {"result": []},
            'https://a.blazemeter.com/api/v4/web/elfinder/1?cmd=open&target=s1_Lw': {"files": []},
            'https://a.blazemeter.com/api/v4/web/elfinder/1?target=s1_Lw&cmd=open': {"files": []},
            'https://a.blazemeter.com/api/v4/workspaces/1': {"result": {"locations": locs}},
        }

        self.mock_post = {}
        self.mock_patch = {}
        self.requests = []

        if obj is not None:
            self.apply(obj)

    def apply(self, obj):
        obj.http_request = self._request_mock

    def _request_mock(self, method, url, **kwargs):
        """
        :param method:
        :param url:
        :param kwargs:
        :rtype: requests.Response
        """
        # TODO: make it simplier, mocking and replacing requests.request of BZAObject
        if method == 'GET':
            resp = self.mock_get[url]
        elif method == 'POST':
            resp = self.mock_post[url]
        elif method == 'PATCH':
            resp = self.mock_patch[url]
        else:
            raise ValueError()

        response = requests.Response()

        if isinstance(resp, list):
            resp = resp.pop(0)

        data = kwargs['data']
        logging.debug("Emulated %s %s %s: %s", method, url, data, resp)
        self.requests.append({"method": method, "url": url, "data": data})
        if isinstance(resp, BaseException):
            raise resp
        response._content = to_json(resp)
        response.status_code = 200
        return response
