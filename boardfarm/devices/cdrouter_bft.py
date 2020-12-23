"""Class to initiate CD-Router testsuite and close the connection to DUT."""

import json
import sys
import time
import traceback
import warnings
from types import SimpleNamespace as bfargs

import numpy
import pandas
from cdrouter import CDRouter
from cdrouter.cdr_error import CDRouterError
from cdrouter.configs import Config
from cdrouter.jobs import Job
from cdrouter.packages import Package


class CDrouterDevice(CDRouter):
    """CDRouter is an industry standard server.

    Used for feature, security, and performance testing of
    broadband and enterprise edge gateways, Wi-Fi APs and mesh systems, VoIP gateways, set-top-boxes,
    and smart hubs enabling the Internet of Things.

    Since CD-Router has its own test-suite, this device class is used to execute test cases on
    the server based on test and board detail provided by boardfarm.
    """

    model = "cdrouter"
    name = "cdrouter"

    class CSVProjectNotFound(AssertionError):
        """Raise an exception if CSV is empty"""

        pass

    class InvalidCDRConfig(AssertionError):
        """Raise an exception if config validation fails"""

        pass

    class InvalidCDRPackage(AssertionError):
        """Raise an exception if config validation fails"""

        pass

    class InvalidCDRJob(AssertionError):
        """Raise an exception if config validation fails"""

        pass

    def __init__(self, *args, **kwargs):
        """Instance initialization.

        This method is to initialize the variables required from board-farm perspective
        to execute the tests and fetch results from CD-router.

        These variables include ipaddress, wan_iface, lan_iface etc.,

        :param ``*args``: set of arguments to be passed if any.
        :type ``*args``: tuple
        :param ``**kwargs``: extra args to be used if any.
        :type ``**kwargs``: dict
        """

        bf_args = bfargs()

        # legacy implementation
        # will have to go
        bf_args.ipaddr = kwargs.pop("ipaddr", "")
        bf_args.wan_iface = kwargs.pop("wan_iface", "")
        bf_args.lan_iface = kwargs.pop("lan_iface", "")
        bf_args.wanispip = kwargs.pop("wanispip", "")
        bf_args.wanispip_v6 = kwargs.pop("wanispip_v6", "")
        bf_args.wanispgateway = kwargs.pop("wanispgateway", "")
        bf_args.wanispgateway_v6 = kwargs.pop("wanispgateway_v6", "")
        bf_args.ipv4hopcount = kwargs.pop("ipv4hopcount", "")

        self.bf_args = bf_args
        self.bf_args.jobs = {}
        self.bf_args.results = []

        # Set this function during runtime, in order to proceed with unpausing a job
        self.unpause_methods = []

        self.bf_args.cdrouter_server = "http://" + self.bf_args.ipaddr
        CDRouter.__init__(self, base=self.bf_args.cdrouter_server)

    def load_csv_project(self, fname, path=""):
        # read the CSV
        file_name = f"{fname}"
        if path:
            file_name = f"{path}/{fname}"
            self.bf_args.path = path

        try:
            with open(file_name, "r") as fp:
                df = pandas.read_csv(fp)
            if len(df) == 0:
                raise CDrouterDevice.CSVProjectNotFound(
                    f"Empty File! name: {file_name}"
                )
        except Exception:
            print(f"Error: Failed to load csv file! name: {file_name}")
            raise

        # Find number of jobs to be triggered.
        # segregate data based on unique jobs
        jobs = numpy.unique(df[["config", "package"]].values.tolist(), axis=0).tolist()
        for idx_key in jobs:
            entries = df[(df["config"] == idx_key[0]) & (df["package"] == idx_key[1])]

            # store all the test IDs and test name based on combinatonal key.
            self.bf_args.jobs[tuple(idx_key)] = entries[
                ["jira_id", "test_name"]
            ].values.tolist()

    def validate_config(self, config):
        try:
            print("Trying to parse config ...\n")
            cfg = self.configs.get_by_name(config)
            check = self.configs.check_config(cfg.contents)

            # code is throwing a bug here.
            # config is compared with only original contents.
            # not the updated one
            print("Warning! : Config contains {} error(s):".format(len(check.errors)))
            for e in check.errors:
                print("    {}: {}".format(e.lines, e.error))
                print("")

            print("Config parsing succeeded!!")
            return True

        except Exception as e:
            print(f"Error: Could not load config : {config}\nParsing Failed!!")
            print(e)
            return False

    def validate_package(self, package, config, testlist):
        """Validate package based on following rules.

        - Check if package exists
        - If package exists, check if correct config id is set.
        - If package exists, check if all input tests are part of the packages' testlist.
          This must be an exact match.

        Any failure in validation, will delete the package and create a new one.
        """
        try:
            print("Trying to parse package ...\n")
            cfg = self.configs.get_by_name(config)
            pkg = self.packages.get_by_name(package)

            if pkg.config_id != cfg.id:
                print(f"Config IDs do not match! cfg : {cfg.id}     pkg : {pkg.id}")
                print(f"Deleting package: {package}!")
                self.packages.delete(pkg.id)
                return False

            if self.packages.testlist_expanded(pkg.id) != list(testlist):
                print("Testlist do not match!")
                print(f"Deleting package: {package}!")
                self.packages.delete(pkg.id)
                return False

            print("Package parsing succeeded!!")
            return True
        except Exception as e:
            print(f"Error: Could not validate package : {package}\nParsing Failed!!")
            print(e)
            return False

    def create_package(self, name, config, test_list):
        invalid_tests = []
        for test in test_list:
            out = self.testsuites.search(test).tests
            if not out:
                invalid_tests.append(test)

        if test_list == invalid_tests:
            raise CDrouterDevice.InvalidCDRPackage("Invalid test list!!")

        if invalid_tests:
            warnings.warn(
                "These are tests which do not exisit in CDRouter.\n"
                f"Following tests are skipped\n{invalid_tests}"
            )

        cfg = self.configs.get_by_name(config)
        p = self.packages.create(
            Package(name=name, testlist=test_list, config_id=cfg.id)
        )
        return p

    def run_jobs(self):
        for job, tests in self.bf_args.jobs.items():

            j = None
            print(f"Loading job with config : {job[0]} and package : {job[1]}")
            print("#" * 80)
            try:
                # if a config does not exist bail out
                config = job[0]
                if not self.validate_config(config):
                    raise CDrouterDevice.InvalidCDRConfig(f"Invalid config : {config}")

                package = job[1]
                testlist = list(zip(*tests))[1]
                if not self.validate_package(package, config, testlist):
                    pkg = self.create_package(package, config, testlist)
                else:
                    pkg = self.packages.get_by_name(package)

                self.bf_args.start_time = time.time()
                j = self.jobs.launch(Job(package_id=pkg.id))

                # if a result_id is attached to a job, it means it's running in CDRouter
                while j.result_id is None:
                    if (time.time() - self.bf_args.start_time) > 300:
                        # delete job if it fails to start
                        self.jobs.delete(j.id)
                        self.bf_args.results.append(None)
                        raise CDrouterDevice.InvalidCDRJob(
                            f"Failed to start CDrouter job for package : {package}"
                        )

                    j = self.jobs.get(j.id)

                print(f"Successfully created job. Result_id : {j.result_id}")

                result = self.results.get(j.result_id)
                self.bf_args.results.append(self.results.get(j.result_id))

                out = self.fetch_results(result)
                for _data in tests:
                    _data.append(out[_data[1]])

            except Exception as e:
                if j:
                    self.cleanup_jobs(j)
                print(
                    f"\n\nFailed to load job with config : {job[0]} and package : {job[1]}"
                )
                for _data in tests:
                    _data.append("error")
                print(e)
                traceback.print_exc(file=sys.stdout)
            finally:
                print("#" * 80, end="\n\n")

    def create_config(self, config_file, path=None):
        # config file must be JSON file
        config_name = config_file.replace(".json", "")
        if path:
            config_file = f"{path}/{config_file}"
        with open(config_file, "r") as fp:
            data = json.load(fp)
            contents = "\n".join([f"testvar {k}\t\t{v}" for k, v in data.items()])
        # create config based on filename
        cfg = self.configs.create(Config(name=config_name, contents=contents))
        return cfg

    def list_packages(self):
        packages = self.cdr.packages.list()
        for i, j in enumerate(packages.data):
            print(f"{i}.) ID: {j.id} \tname:{j.name}")

    def stop_result(self, result):
        self.bf_args.start_time = time.time()
        while result.status != "stopped":
            time.sleep(2)
            try:
                self.results.stop(result.id)
            except CDRouterError:
                break
            if (time.time() - self.bf_args.start_time) > 300:
                print("Please stop this job manually..")
                raise CDrouterDevice.InvalidCDRJob(
                    f"Failed to stop Job result : {result.id}"
                )
            result = self.results.get(result.id)

    def cleanup_jobs(self, job):
        result = None
        try:
            result = self.results.get(job.result_id)
        except CDRouterError:
            pass
        if result:
            if result.status in ["paused", "running"]:
                self.stop_result(result)

        # Brute force logic, to delete the job.
        for _ in range(5):
            try:
                time.sleep(2)
                self.jobs.delete(job.id)
            except CDRouterError:
                break
        else:
            raise CDrouterDevice.InvalidCDRJob(f"Failed to delete Job : {job.id}")

    def fetch_results(self, result):
        test_running = True
        for fn in self.unpause_methods:
            unpaused = False
            while unpaused is not True:
                r = self.results.get(result.id)

                if r.status == "paused":
                    fn()
                    self.results.unpause(result.id)
                    unpaused = True

                if r.status not in ["running", "paused"]:
                    test_running = False
                    break

                time.sleep(1)
            else:
                continue
            break

        while test_running:
            r = self.results.get(result.id)
            if r.status == "paused":
                print("Error: test is still paused")
                self.stop_result(r)
                break

            if r.status != "running" and r.status != "paused":
                break

            time.sleep(5)

        print(r.result)
        summary = self.results.summary_stats(result.id)

        output = {}
        for test in summary.test_summaries:
            if str(test.name) not in ["start", "final"]:
                try:
                    output[test.name] = test.result
                except AttributeError:
                    # In case test does not have attribute result.
                    output[test.name] = "error"

        return output
