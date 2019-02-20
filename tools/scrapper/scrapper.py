from driver import init_driver
from bs4 import BeautifulSoup
import logging
import json
import datetime


class Scrapper:

    def __init__(self):
        with open("config.json", "r") as fp:
            self.config = json.load(fp)["scrapper"]

        self.logger = logging.getLogger("scrapper")
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(self.config["logger_format"])
        fh = logging.FileHandler(self.config["logger"], mode="w")
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        now = datetime.datetime.now()
        self.output_dir = str(now.strftime("%Y-%m-%d_%H:%M"))
        self.rescan_page = ""

        try:
            self.scan_flag = "yes"  # initial scan flag.
            self.scrapper_option = {
                "func_call": {
                    "yes": {1: self.scan, 2: self.search, 3: self.stop_scrapper},
                    "no": {1: self.scan, 2: self.search, 3: self.rescan, 4: self.save, 5: self.stop_scrapper}
                }
            }
            with open(self.config["page_list"]) as fp:
                self.page_keys = [i for i in fp.read().strip().split("\n") if i != ""]
                self.scrapper_dict = {i: {} for i in self.page_keys}

            driver_choice = self.config["browser"]
            self.__driver = init_driver(driver_choice)
            self.logger.info("Driver initialization - Success!")
        except Exception as e:
            self.logger.error(type(e).__name__ + " - " + str(e))
            self.logger.error("Exiting Program.")
            exit(1)

    def start_scrapper(self):
        try:
            self.__driver.get(self.config["URL"])
            self.__driver.verify_page_load()
            self.logger.info("URL loaded successfully: " + self.config["URL"])

            menu = self.scrapper_option["func_call"][self.scan_flag]
            choice = 1
            while menu[choice] != self.stop_scrapper:
                try:
                    choice = int(self.main_menu())
                    if choice not in menu.keys():
                        raise ValueError("Index out of range")

                    self.logger.info("Function call : " + menu[choice].__name__)
                    menu[choice]()
                    menu = self.scrapper_option["func_call"][self.scan_flag]

                except (ValueError, NameError) as e:
                    self.logger.error(type(e).__name__ + " - " + str(e))
                    print("Invalid Option. Try Again!!")
                    choice = 1

        except Exception as e:
            self.logger.exception(e)
            self.stop_scrapper(True)

    def main_menu(self):
        try:
            print("\nSelect an option:")
            menu = [str(opt) + ". " + func.__name__
                    for opt, func in self.scrapper_option["func_call"][self.scan_flag].iteritems()]
            print("\t\t".join(menu))
            return raw_input("Enter : ")
        except Exception as e:
            print("Error : Exiting Code. Please check /logs/scrapper.log")
            self.logger.error(type(e).__name__ + " - " + str(e))
            raise e

    def search(self):
        try:
            keyword = raw_input('search-keyword (enter "all" to list) : ')
            self.logger.info("keyword searched : " + keyword)
            flag = False
            if keyword.strip().lower() == "all":
                print("\n".join(self.scrapper_dict.keys()))
            else:
                for i in self.scrapper_dict.keys():
                    if i.startswith(keyword):
                        print(i)
                        flag = True
            if not flag:
                print("No pages identified with keyword : " + keyword)
        except Exception as e:
            print("Error : " + str(e))
            self.logger.error(type(e).__name__ + " - " + str(e))

    def scan(self):
        try:
            raw_input("\nNavigate to the page you want to scan.\nPress Enter to continue (Enter)")
            page_name = raw_input("Enter page name: ").strip().lower()
            self.logger.info("Page entered : " + page_name)
            if page_name not in self.scrapper_dict.keys():
                choice = raw_input("This page is not available in list!\nWould you like to add (Y/N): ")
                if choice.strip().lower() not in ["", "y", "yes"]:
                    print("Skipping current page!")
                    return
                self.scrapper_dict[page_name] = {}
                print("Added page to list : " + page_name)
                self.logger.info("Added page to list : " + page_name)

            if self.scan_flag == "yes":
                self.logger.info("Initial scan flag unset. Changing menu options")
                self.scan_flag = "no"

            self.__driver.scan_html(self.scrapper_dict[page_name])
            self.rescan_page = page_name

        except Exception as e:
            print("Error : " + str(e))
            self.logger.error(type(e).__name__ + " - " + str(e))

    def save(self):
        try:
            # section for gui_conf : page list
            page_list_details = self.config["result_dir"]+"page_list_"+self.output_dir
            with open(page_list_details, "w") as fp:
                fp.write("\n".join(self.scrapper_dict.keys()))
            self.logger.info("Created page_list copy : "+page_list_details)

            scrap_file = self.config["result_dir"]+"result_"+self.output_dir+".json"
            with open(scrap_file, "w") as fp:
                json.dump(self.scrapper_dict,fp,indent=5)
            self.logger.info("Result generated : " + page_list_details)

            print("Scan result saved in : "+"/".join(scrap_file.split("/")[-2:]))

        except Exception as e:
            print("Error : " + str(e))
            self.logger.error(type(e).__name__ + " - " + str(e))

    def rescan(self):
        choice = raw_input("Would you like to rescan : "+self.rescan_page+"\n(Y/N): ")
        if choice.strip().lower() not in ["", "y", "yes"]:
            print("Skipping current page!")
            return
        self.__driver.scan_html(self.scrapper_dict[self.rescan_page])

    def stop_scrapper(self,exception_flag=False):
        if not exception_flag:
            choice = raw_input("Would you like to save current progress (Y/N): ")
            if choice.strip().lower() in ["", "y", "yes"]:
                self.save()
        self.__driver.close()
        exit(0)


obj = Scrapper()
obj.start_scrapper()